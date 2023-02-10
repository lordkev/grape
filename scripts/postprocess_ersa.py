import polars as pl
import pandas
import numpy
import os
import logging
from collections import Counter
from utils.ibd import read_king_segments as rks, interpolate_all


def is_non_zero_file(fpath):
    return os.path.isfile(fpath) and os.path.getsize(fpath) > 0


def _sort_ids(data):
    return data.with_columns(
        pl.when(pl.col('id2') < pl.col('id1'))
        .then(
            pl.struct([
                pl.col('id2').alias('id1'),
                pl.col('id1').alias('id2')
            ])
        )
        .otherwise(
            pl.struct([
                pl.col('id1').alias('id1'),
                pl.col('id2').alias('id2')
            ])
        )
    ).drop('id2').unnest('id1')


def read_ibis(ibd_path):
    # sample1 sample2 chrom phys_start_pos phys_end_pos IBD_type
    # genetic_start_pos genetic_end_pos genetic_seg_length marker_count error_count error_density
    names = [
        'sample1',
        'sample2'
        'chrom',
        'phys_start_pos',
        'phys_end_pos',
        'IBD_type',
        'genetic_start_pos',
        'genetic_end_pos',
        'genetic_seg_length',
        'marker_count',
        'error_count',
        'error_density'
    ]
    data = pl.read_csv(ibd_path, has_header=False, columns=names, sep='\t')
    data = data.with_columns(
        pl.col('id1').str.replace(':', '_'),
        pl.col('id2').str.replace(':', '_')
    )
    data = _sort_ids(data)
    ibd2_info = (
        data
        .select(['id1', 'id2', 'chrom', 'genetic_seg_length'])
        .filter((pl.col('IBD_type') == 'IBD2'))
        .groupby(['id1', 'id2'])
        .agg([
            pl.col('chrom').count(),
            pl.col('genetic_seg_length').sum()
            ])
        )
    ibd2_info = ibd2_info.rename({'genetic_seg_length': 'total_seg_len_ibd2', 'chrom': 'seg_count_ibd2'})
    print(ibd2_info)
    return ibd2_info


def read_ersa(ersa_path):
    # Indv_1     Indv_2      Rel_est1      Rel_est2      d_est     lower_d  upper_d     N_seg     Tot_cM
    data = pl.read_csv(ersa_path, has_header=False, sep='\t',
                             names=['id1', 'id2', 'rel_est1', 'rel_est2',
                                    'ersa_degree', 'ersa_lower_bound', 'ersa_upper_bound', 'seg_count', 'total_seg_len'],
                             dtypes={'ersa_degree': str, 'ersa_lower_bound': str, 'ersa_upper_bound': str,
                                    'seg_count': str, 'total_seg_len': str})

    data = data.filter((pl.col('rel_est1') != 'NA') | (pl.col('rel_est2') != 'NA'))
    data = data.with_columns([
        pl.col('id1').str.strip(),
        pl.col('id2').str.strip()
    ])
    data = _sort_ids(data)
    data = data.with_columns([
        pl.col('ersa_degree').str.strip().cast(pl.Int32),
        pl.col('ersa_lower_bound').str.strip().cast(pl.Int32),
        pl.col('ersa_upper_bound').str.strip().cast(pl.Int32),
        pl.col('seg_count').str.strip().cast(pl.Int32),
        pl.col('seg_count').str.strip().cast(pl.Int32),
        pl.col('total_seg_len').str.replace(',', '').str.strip().cast(pl.Float64)
    ])
    found = data.select([pl.col('total_seg_len').where(pl.col('total_seg_len') > 1000).sum()])
    print(f'parsed total_seg_len, found {found[0, 0]} long entries')

    data = data.with_columns(
        pl.when(pl.col('ersa_lower_bound') != 1)
        .then(pl.col('ersa_lower_bound') - 1),
        pl.when(pl.col('ersa_upper_bound') != 1)
        .then(pl.col('ersa_upper_bound') - 1)
    )

    logging.info(f'read {data.shape[0]} pairs from ersa output')
    logging.info(f'ersa after reading has {pandas.notna(data.ersa_degree).sum()}')
    data = data.select(['id1', 'id2', 'ersa_degree', 'ersa_lower_bound', 'ersa_upper_bound', 'seg_count', 'total_seg_len'])\
        .filter(pl.col('id1') != pl.col('id2'))  # Removed .set_index(['id1', 'id2'])
    return data


if __name__ == '__main__':

    logging.basicConfig(filename=snakemake.log[0], level=logging.DEBUG, format='%(levelname)s:%(asctime)s %(message)s')

    ibd_path = snakemake.input['ibd']
    # within families
    # across families
    ersa_path = snakemake.input['ersa']
    output_path = snakemake.output[0]

    ibd = read_ibis(ibd_path)
    ersa = read_ersa(ersa_path)

    if ibd.is_empty() or ersa.is_empty():
        logging.error("ersa postprocess input is empty")
        open(output_path, "w").close()  # create empty output to avoid error
        quit()

    logging.info(f'ibd shape: {ibd.shape[0]}, ersa shape: {ersa.shape[0]}')
    relatives = ibd.join(ersa, how='outer')  # No left_index / right_index input params

    # It is impossible to have more than 50% of ibd2 segments unless you are monozygotic twins or duplicates.
    GENOME_CM_LEN = 3440
    DUPLICATES_THRESHOLD = 1750
    FS_TOTAL_THRESHOLD = 2100
    FS_IBD2_THRESHOLD = 450
    dup_mask = pl.col('total_seg_len_ibd2') > DUPLICATES_THRESHOLD
    fs_mask = (pl.col('total_seg_len') > FS_TOTAL_THRESHOLD) & (pl.col('total_seg_len_ibd2') > FS_IBD2_THRESHOLD) & (~dup_mask)
    po_mask = (pl.col('total_seg_len') / GENOME_CM_LEN > 0.8) & (~fs_mask) & (~dup_mask)
    print(f'We have {len(relatives.filter(dup_mask))} duplicates, '
          f'{len(relatives.filter(fs_mask))} full siblings and '
          f'{len(relatives.filter(po_mask))} parent-offspring relationships')

    relatives = relatives.with_columns([
        pl.when(dup_mask)
        .then(0)
        .otherwise(pl.col('ersa_degree'))
        .alias('final_degree'),

        pl.when(dup_mask)
        .then('MZ/Dup')
        .otherwise(pl.col('ersa_degree'))
        .alias('relation'),

        pl.when(po_mask)
        .then(1)
        .otherwise(pl.col('ersa_degree'))
        .alias('final_degree'),

        pl.when(po_mask)
        .then('PO')
        .otherwise(pl.col('ersa_degree'))
        .alias('relation'),

        pl.when((~po_mask) & (pl.col('ersa_degree') == 1))
        .then(2)
        .otherwise(pl.col('ersa_degree'))
        .alias('final_degree'),

        pl.when(fs_mask)
        .then(2)
        .otherwise(pl.col('ersa_degree'))
        .alias('final_degree'),

        pl.when(fs_mask)
        .then('FS')
        .otherwise(pl.col('ersa_degree'))
        .alias('relation'),

        pl.col('total_seg_len_ibd2')
        .fill_null(pl.lit(0)),

        pl.col('seg_count_ibd2')
        .fill_null(pl.lit(0))
    ])
    '''
        IBIS and ERSA do not distinguish IBD1 and IBD2 segments
        shared_genome_proportion is a proportion of identical alleles
        i.e. shared_genome_proportion of [(0/0), (0/1)] and [(0/0), (1/1)] should be 3/4
        GENOME_SEG_LEN is length of centimorgans of the haplotype
        ibd2 segments span two haplotypes, therefore their length should be doubled
        total_seg_len includes both ibd1 and ibd2 segments length
    '''
    shared_genome_formula = (pl.col('total_seg_len') - pl.col('total_seg_len_ibd2')) / (2*GENOME_CM_LEN) + pl.col('total_seg_len_ibd2')*2 / (2*GENOME_CM_LEN)
    relatives = relatives.with_columns(
        pl.when(shared_genome_formula > 1)
        .then(1)
        .otherwise(shared_genome_formula)
        .alias('shared_genome_proportion')
    )
    logging.info(f'final degree not null: {len(relatives["final_degree"]) - relatives["final_degree"].null_count()}')
    relatives = relatives.filter(pl.col('final_degree').is_null() == False)
    relatives.write_csv(output_path, sep='\t')
