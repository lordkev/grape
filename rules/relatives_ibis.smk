import os
import sys


rule ibis:
    input:
        bed = "preprocessed/data.bed",
        fam = "preprocessed/data.fam",
        bim = "preprocessed/data_mapped.bim"
    conda:
        "ibis"
    output:
        ibd = "ibis/merged_ibis.seg"
    log:
        "logs/ibis/run_ibis.log"
    benchmark:
        "benchmarks/ibis/run_ibis.txt"
    threads: workflow.cores
    params:
        mL = config['ibis_seg_len'],
        mT = config['ibis_min_snp']
    shell:
        """
        ibis {input.bed} {input.bim} {input.fam} -t {threads} -mt {params.mT} -mL {params.mL} -ibd2 -mL2 3 -hbd -f ibis/merged_ibis |& tee -a {log}
        """


WEIGHTED_IBD_SEGMENTS_FOLDER = 'ibis-weighted'
SNAKEFILE_FOLDER = os.path.dirname(workflow.snakefile)


if config.get('weight_mask'):
    rule ibis_segments_weighing:
        input:
            ibd = rules.ibis.output.ibd,
            script = os.path.join(SNAKEFILE_FOLDER, '../weight/apply_weight_mask.py')
        conda:
            'weight-mask'
        output:
            ibd = os.path.join(WEIGHTED_IBD_SEGMENTS_FOLDER, 'ibis_weighted.seg'),
        params:
            mask = config['weight_mask']
        shell:
            """
            python {input.script} \
                --input-ibd-segments-file {input.ibd} \
                --mask-file {params.mask} \
                --output-ibd-segments-file {output.ibd}
            """
    ibd_segments_file = rules.ibis_segments_weighing.output.ibd
else:
    ibd_segments_file = rules.ibis.output.ibd


checkpoint transform_ibis_segments:
    input:
        ibd = ibd_segments_file,
        fam = "preprocessed/data.fam"
    output:
        bucket_dir = directory("ibd")
    log:
        "logs/ibis/transform_ibis_segments.log"
    conda:
        "evaluation"
    script:
        "../scripts/transform_ibis_segments.py"


def aggregate_input(wildcards):
    checkpoints.transform_ibis_segments.get()
    ids = glob_wildcards(f"ibd/{{id}}.tsv").id
    return expand(f"ibd/{{id}}.tsv", id=ids)


rule ersa:
    input:
        ibd = aggregate_input
    output:
        "ersa/relatives.tsv"
    conda:
        "ersa"
    log:
        "logs/ersa/ersa.log"
    benchmark:
        "benchmarks/ersa/ersa.txt"
    params:
        l = config['zero_seg_count'],
        th = config['zero_seg_len'],
        a = config['alpha'],
        t = config['ibis_seg_len'],
        r = '--nomask ' + '-r ' + str(config['ersa_r']) if config.get('weight_mask') else ''
    shell:
        """
        touch {output}
        FILES="{input.ibd}"
        TEMPFILE=ersa/temp_relatives.tsv
        rm -f $TEMPFILE
        rm -f {output}

        for input_file in $FILES; do
            ersa --avuncular-adj -ci -a {params.a} --dmax 14 -t {params.t} -l {params.l} \
                {params.r} -th {params.th} $input_file -o $TEMPFILE |& tee {log}

            if [[ "$input_file" == "${{FILES[0]}}" ]]; then
                cat $TEMPFILE >> {output}
            else
                sed 1d $TEMPFILE >> {output}
            fi
        done
        """


rule postprocess_ersa:
    input:
        ibd=rules.ibis.output['ibd'],
        ersa=rules.ersa.output[0]
    params:
        ibis = True
    output: "results/relatives.tsv"
    conda: "evaluation"
    log: "logs/merge/postprocess-ersa.log"
    script: "../scripts/postprocess_ersa.py"
