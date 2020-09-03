# GenX relatives detection pipeline

### Snakemake launch

    snakemake --cores all --use-conda --use-singularity --singularity-prefix=/media --singularity-args="-B /media:/media" -p all

## Visualization of the DAG

    nakemake --dag all | dot -Tsvg > dag.svg

```shell script
snakemake --cores all --use-conda --use-singularity --singularity-prefix=/media --singularity-args="-B /media:/media" -p all
```

### Force-launch single rule

```shell script
snakemake --cores all --use-conda --use-singularity --singularity-prefix=/media --singularity-args="-B /media:/media" -R somerule --until somerule
```

### Simulate data

```shell script
snakemake --cores all --use-conda --use-singularity --singularity-prefix=/media --singularity-args="-B /media:/media" -p -s workflows/pedsim/Snakefile
```

