# GenX relatives detection pipeline

## Snakemake launch

    snakemake --cores all --use-conda --use-singularity --singularity-prefix=/media --singularity-args="-B /media:/media" -p all

## Visualization of the DAG

    nakemake --dag all | dot -Tsvg > dag.svg
