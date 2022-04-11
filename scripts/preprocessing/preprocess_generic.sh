#! /bin/bash

# calling process needs to set:
# base
# $src
# $trg
# $model_name
# $dry_run
# $seed
# $multilingual
# $language_pairs

base=$1
src=$2
trg=$3
model_name=$4
dry_run=$5
seed=$6
multilingual=$7
language_pairs=$8

data=$base/data
venvs=$base/venvs
scripts=$base/scripts
shared_models=$base/shared_models

mkdir -p $shared_models

# subfolders

data_sub=$data/${src}-${trg}
shared_models_sub=$shared_models/${src}-${trg}

# overwrite subfolder names to make it easier to read

data_sub=$data_sub/$model_name
shared_models_sub=$shared_models_sub/$model_name

mkdir -p $shared_models_sub

source activate $venvs/sockeye3

MOSES=$base/tools/moses-scripts/scripts
TOKENIZER=$MOSES/tokenizer

DRY_RUN_TRAIN_SIZE=14000
DRY_RUN_DEVTEST_SIZE=2

DEVTEST_MAXSIZE=5000

SMALLEST_TRAINSIZE=10000
SMALL_TRAINSIZE=100000
MEDIUM_TRAINSIZE=500000
LARGE_TRAINSIZE=1000000
LARGEST_TRAINSIZE=10000000

TRAIN_SLICE_SMALL=1000
TRAIN_SLICE_MEDIUM=2500
TRAIN_SLICE_LARGE=5000

SENTENCEPIECE_MAX_LINES=10000000

CORPORA_EXCEPT_TRAIN="dev test"
ALL_CORPORA="$CORPORA_EXCEPT_TRAIN train"

echo "data_sub: $data_sub"

# measure time

SECONDS=0

#################

if [[ -f $data_sub/test.pieces.src ]]; then
    echo "File already exists: $data_sub/test.pieces.src"
    echo "Skipping. Delete files to repeat step."
    exit 0
fi

# put together training data and correctly assign ".src" and ".trg" suffixes

echo -n "" > $data_sub/train.src
echo -n "" > $data_sub/train.trg

for pair in "${language_pairs[@]}"; do
    pair=($pair)

    corpus=${pair[0]}
    src=${pair[1]}
    trg=${pair[2]}

    cat $data_sub/$corpus.$src >> $data_sub/train.src
    cat $data_sub/$corpus.$trg >> $data_sub/train.trg
done

# set aside held-out slices of the training data (size of slice depending on total size)
# for testing and development

# determine $train_slice_size

num_lines=$(cat $data_sub/train.src | wc -l)

if [[ $num_lines -gt ${LARGEST_TRAINSIZE} ]]; then
    train_slice_size=$TRAIN_SLICE_LARGE
elif [[ $num_lines -gt ${LARGE_TRAINSIZE} ]]; then
    train_slice_size=$TRAIN_SLICE_LARGE
elif [[ $num_lines -gt ${MEDIUM_TRAINSIZE} ]]; then
    train_slice_size=$TRAIN_SLICE_LARGE
elif [[ $num_lines -gt ${SMALL_TRAINSIZE} ]]; then
    train_slice_size=$TRAIN_SLICE_MEDIUM
elif [[ $num_lines -gt ${SMALLEST_TRAINSIZE} ]]; then
    train_slice_size=$TRAIN_SLICE_SMALL
else
    echo "Warning: training data size too small"
    exit 1
fi

echo "train_slice_size=$train_slice_size"

for slice_corpus in $CORPORA_EXCEPT_TRAIN; do

    if [[ ! -f $data_sub/train.shuffled.both ]]; then

        paste $data_sub/train.src $data_sub/train.trg > $data_sub/train.both

        python $scripts/preprocessing/shuffle_with_seed.py \
            --seed $seed --input $data_sub/train.both \
            > $data_sub/train.shuffled.both
    fi

    head -n $train_slice_size $data_sub/train.shuffled.both | cut -f1 > $data_sub/$slice_corpus.src
    head -n $train_slice_size $data_sub/train.shuffled.both | cut -f2 > $data_sub/$slice_corpus.trg

    # remove first $train_slice_size pairs from the training data

    sed -i -e 1,${train_slice_size}d $data_sub/train.shuffled.both

done

# restore per-language files

cut -f1 $data_sub/train.shuffled.both > $data_sub/train.src
cut -f2 $data_sub/train.shuffled.both > $data_sub/train.trg

rm $data_sub/train.both $data_sub/train.shuffled.both

# truncate dev and/or test data to $DEVTEST_MAXSIZE if too large

for corpus in $CORPORA_EXCEPT_TRAIN; do
    num_lines_src=$(cat $data_sub/$corpus.src | wc -l)

    if [[ $num_lines_src -gt $DEVTEST_MAXSIZE ]]; then
        for lang in src trg; do
            mv $data_sub/$corpus.$lang $data_sub/$corpus.$lang.big
            head -n $DEVTEST_MAXSIZE $data_sub/$corpus.$lang.big > $data_sub/$corpus.$lang
        done
    fi
done

# truncate all data if dry run

if [[ $dry_run == "true" ]]; then
    for lang in src trg; do
        for corpus in $CORPORA_EXCEPT_TRAIN; do
            mv $data_sub/$corpus.$lang $data_sub/$corpus.$lang.big
            head -n $DRY_RUN_DEVTEST_SIZE $data_sub/$corpus.$lang.big > $data_sub/$corpus.$lang
        done

        mv $data_sub/train.$lang $data_sub/train.$lang.big
        head -n $DRY_RUN_TRAIN_SIZE $data_sub/train.$lang.big > $data_sub/train.$lang
    done
fi

# prenormalization for train data

for corpus in $ALL_CORPORA; do
    for lang in src trg; do
        cat $data_sub/$corpus.$lang | \
        perl -CS -pe 'tr[\x{9}\x{A}\x{D}\x{20}-\x{D7FF}\x{E000}-\x{FFFD}\x{10000}-\x{10FFFF}][]cd;' | \
        perl -CS -pe 's/\&\s*\#\s*160\s*\;/ /g' \
        > $data_sub/$corpus.prenorm.$lang
    done
done

# normalize train data

for lang in src trg; do
    cat $data_sub/train.prenorm.$lang | \
    ${TOKENIZER}/replace-unicode-punctuation.perl | \
    ${TOKENIZER}/remove-non-printing-char.perl | \
    ${TOKENIZER}/deescape-special-chars.perl | \
    sed 's/  */ /g;s/^ *//g;s/ *$//g' > \
        $data_sub/train.normalized.$lang
done

# normalize dev / test data + other test corpora

for corpus in $CORPORA_EXCEPT_TRAIN; do
    for lang in src trg; do
        cat $data_sub/$corpus.prenorm.$lang | \
        ${TOKENIZER}/replace-unicode-punctuation.perl | \
        ${TOKENIZER}/remove-non-printing-char.perl | \
        ${TOKENIZER}/deescape-special-chars.perl | \
        sed 's/  */ /g;s/^ *//g;s/ *$//g' > \
            $data_sub/$corpus.normalized.$lang
    done
done

# remove sentences from dev if source or target is empty
# (otherwise leads to potential Sockeye error)

for lang in src trg; do
    mv $data_sub/dev.normalized.$lang $data_sub/dev.before_remove_empty.$lang
done

python $scripts/preprocessing/remove_if_source_or_target_empty.py \
    --input-src $data_sub/dev.before_remove_empty.src \
    --input-trg $data_sub/dev.before_remove_empty.trg \
    --output-src $data_sub/dev.normalized.src \
    --output-trg $data_sub/dev.normalized.trg

# determine $sentencepiece_vocab_size

num_lines=$(cat $data_sub/train.normalized.src | wc -l)

if [[ $num_lines -gt ${LARGEST_TRAINSIZE} ]]; then
    sentencepiece_vocab_size=16000
elif [[ $num_lines -gt ${LARGE_TRAINSIZE} ]]; then
    sentencepiece_vocab_size=16000
elif [[ $num_lines -gt ${MEDIUM_TRAINSIZE} ]]; then
    sentencepiece_vocab_size=12000
elif [[ $num_lines -gt ${SMALL_TRAINSIZE} ]]; then
    sentencepiece_vocab_size=4000
elif [[ $num_lines -gt ${SMALLEST_TRAINSIZE} ]]; then
    sentencepiece_vocab_size=1000
else
    echo "Warning: training data size too small"
    exit 1
fi

echo "sentencepiece_vocab_size=$sentencepiece_vocab_size"

# learn sentencepiece model on train (concatenate both languages)

for lang in src trg; do
    if [[ ! -f $shared_models_sub/$lang.sentencepiece.model ]]; then

      # determine character coverage

      num_characters=$(head -n 1000000 $data_sub/train.normalized.$lang | python $scripts/preprocessing/num_chars.py | wc -l)

      if [[ $num_characters -gt 1000 ]]; then
          character_coverage=0.9995
      else
          character_coverage=1.0
      fi

      python $scripts/preprocessing/train_sentencepiece.py \
        --model-prefix $shared_models_sub/$lang.sentencepiece \
        --input $data_sub/train.normalized.$lang \
        --vocab-size $sentencepiece_vocab_size \
        --character-coverage $character_coverage \
        --input-sentence-size=$SENTENCEPIECE_MAX_LINES

    else
      echo "Sentencepiece model exists: $shared_models_sub/$lang.sentencepiece.model"
      echo "Skipping model training"
    fi
done

# apply SP model to train, test and dev

for corpus in $ALL_CORPORA; do
    for lang in src trg; do
        cat $data_sub/$corpus.normalized.$lang | \
            python $scripts/preprocessing/apply_sentencepiece.py \
                --model $shared_models_sub/$lang.sentencepiece.model \
                    > $data_sub/$corpus.pieces.$lang
    done
done

# ratio etc filter

$MOSES/training/clean-corpus-n.perl $data_sub/train.pieces src trg $data_sub/train.clean 1 250

# sizes
echo "Sizes of all files:"

wc -l $data_sub/*
wc -l $shared_models_sub/*

echo "time taken:"
echo "$SECONDS seconds"
