#! /bin/bash

# calling process needs to set:
# base
# $src
# $trg
# $model_name
# $dry_run
# $testing_corpora
# $multilingual

base=$1
src=$2
trg=$3
model_name=$4
dry_run=$5
testing_corpora=$6
multilingual=$7

venvs=$base/venvs
scripts=$base/scripts

source activate $venvs/sockeye3

beam_size="5"
batch_size="64"
length_penalty_alpha="1.0"

data=$base/data
data_sub=$data/${src}-${trg}
data_sub_sub=$data_sub/$model_name

models=$base/models
models_sub=$models/${src}-${trg}
models_sub_sub=$models_sub/$model_name

translations=$base/translations
translations_sub=$translations/${src}-${trg}
translations_sub_sub=$translations_sub/$model_name

# fail with non-zero status if there is no model checkpoint,
# to signal to downstream dependencies that they cannot be satisfied

if [[ ! -e $models_sub_sub/params.best ]]; then
    echo "There is no single model checkpoint, file does not exist:"
    echo "$models_sub_sub/params.best"
    exit 1
fi

mkdir -p $translations_sub_sub

# beam translation

for corpus in $testing_corpora; do
    input=$data_sub_sub/$corpus.pieces.src
    output_pieces=$translations_sub_sub/$corpus.pieces.trg
    output=$translations_sub_sub/$corpus.trg

    . $scripts/translation/translate_more_generic.sh
done
