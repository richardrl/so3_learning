import pykitti
from matplotlib import pyplot as plt
import numpy as np
import torch
from liegroups import SE3, SO3
from pyslam.utils import invsqrt
from pyslam.metrics import TrajectoryMetrics
from optparse import OptionParser
from fusion_pipeline import SO3FusionPipeline
from pyslam.visualizers import TrajectoryVisualizer

import copy
import time
import os, glob
import pickle
import csv

import argparse

parser = argparse.ArgumentParser(description='SO(3) Fusion')
parser.add_argument('--seq', '-s', default='00', type=str,
                    help='which sequence to test')


def run_fusion(baseline_metrics_file, hydranet_output_file, add_reverse_factor):

    tm_vo = TrajectoryMetrics.loadmat(baseline_metrics_file)
    T_w_c_vo = tm_vo.Twv_est
    T_w_c_gt = tm_vo.Twv_gt

    Sigma_21_vo = tm_vo.mdict['Sigma_21']
    fusion_pipeline = SO3FusionPipeline(T_w_c_vo, Sigma_21_vo, T_w_c_gt, hydranet_output_file, add_reverse_factor=add_reverse_factor, first_pose=T_w_c_vo[0])
    
    #The magic!
    fusion_pipeline.compute_fused_estimates()
    
    #Compute statistics
    T_w_c_est = [T for T in fusion_pipeline.T_w_c]
    tm = TrajectoryMetrics(tm_vo.Twv_gt, T_w_c_est, convention='Twv')

    return tm




def make_topdown_plot(tm, outfile=None):
    pos_gt = np.array([T.trans for T in tm.Twv_gt])
    pos_est = np.array([T.trans for T in tm.Twv_est])

    f, ax = plt.subplots()

    ax.plot(pos_gt[:, 0], pos_gt[:, 1], '-k',
            linewidth=2, label='Ground Truth')
    ax.plot(pos_est[:, 0], pos_est[:, 1], label='VO')

    ax.axis('equal')
    ax.minorticks_on()
    ax.grid(which='both', linestyle=':', linewidth=0.2)
    ax.set_title('Trajectory')
    ax.set_xlabel('Easting (m)')
    ax.set_ylabel('Northing (m)')
    ax.legend()

    if outfile:
        print('Saving to {}'.format(outfile))
        f.savefig(outfile)

    return f, ax


def make_segment_err_plot(tm, segs, outfile=None):
    segerr, avg_segerr = tm.segment_errors(segs)

    f, ax = plt.subplots(1, 2, figsize=(12, 4))

    ax[0].plot(avg_segerr[:, 0], avg_segerr[:, 1] * 100., '-s')
    ax[1].plot(avg_segerr[:, 0], avg_segerr[:, 2] * 180. / np.pi, '-s')

    ax[0].minorticks_on()
    ax[0].grid(which='both', linestyle=':', linewidth=0.2)
    ax[0].set_title('Translational error')
    ax[0].set_xlabel('Sequence length (m)')
    ax[0].set_ylabel('Average error (\%)')

    ax[1].minorticks_on()
    ax[1].grid(which='both', linestyle=':', linewidth=0.2)
    ax[1].set_title('Rotational error')
    ax[1].set_xlabel('Sequence length (m)')
    ax[1].set_ylabel('Average error (deg/m)')

    if outfile:
        print('Saving to {}'.format(outfile))
        f.savefig(outfile)

    return f, ax


def main():
    # Odometry sequences
    # Nr.     Sequence name     Start   End
    # ---------------------------------------
    # 00: 2011_10_03_drive_0027 000000 004540
    # 01: 2011_10_03_drive_0042 000000 001100
    # 02: 2011_10_03_drive_0034 000000 004660
    # 03: 2011_09_26_drive_0067 000000 000800
    # 04: 2011_09_30_drive_0016 000000 000270
    # 05: 2011_09_30_drive_0018 000000 002760
    # 06: 2011_09_30_drive_0020 000000 001100
    # 07: 2011_09_30_drive_0027 000000 001100
    # 08: 2011_09_30_drive_0028 001100 005170
    # 09: 2011_09_30_drive_0033 000000 001590
    # 10: 2011_09_30_drive_0034 000000 001200

    seqs = {'00': {'date': '2011_10_03',
                   'drive': '0027',
                   'frames': range(0, 4541)},
            '01': {'date': '2011_10_03',
                   'drive': '0042',
                   'frames': range(0, 1101)},
            '02': {'date': '2011_10_03',
                   'drive': '0034',
                   'frames': range(0, 4661)},
            '04': {'date': '2011_09_30',
                   'drive': '0016',
                   'frames': range(0, 271)},
            '05': {'date': '2011_09_30',
                   'drive': '0018',
                   'frames': range(0, 2761)},
            '06': {'date': '2011_09_30',
                   'drive': '0020',
                   'frames': range(0, 1101)},
            '07': {'date': '2011_09_30',
                   'drive': '0027',
                   'frames': range(0, 1101)},
            '08': {'date': '2011_09_30',
                   'drive': '0028',
                   'frames': range(1100, 5171)},
            '09': {'date': '2011_09_30',
                   'drive': '0033',
                   'frames': range(0, 1591)},
            '10': {'date': '2011_09_30',
                   'drive': '0034',
                   'frames': range(0, 1201)}}

    process_seqs = {'00', '02', '05'}
    add_reverse_factor = False

    for seq in process_seqs:
        tm_path = '../svo/baseline_tm/'
        fusion_tm_output_path = 'fusion_tms/'
        hydranet_output_file = 'hydranet_output_reverse_model_seq_{}.pt'.format(seq)

        fusion_metrics_file = os.path.join(fusion_tm_output_path, 'SO3_fused_single_{}_drive_{}.mat'.format(seqs[seq]['date'], seqs[seq]['drive']))
        orig_metrics_file = os.path.join(tm_path, '{}_drive_{}.mat'.format(seqs[seq]['date'],seqs[seq]['drive']))


        tm_baseline = TrajectoryMetrics.loadmat(orig_metrics_file)
        tm_fusion = run_fusion(orig_metrics_file, hydranet_output_file, add_reverse_factor)

        # Compute errors
        trans_armse_fusion, rot_armse_fusion = tm_fusion.mean_err(error_type='rel', rot_unit='deg')
        trans_armse_vo, rot_armse_vo = tm_baseline.mean_err(error_type='rel', rot_unit='deg')

        trans_armse_fusion_traj, rot_armse_fusion_traj = tm_fusion.mean_err(error_type='traj', rot_unit='deg')
        trans_armse_vo_traj, rot_armse_vo_traj = tm_baseline.mean_err(error_type='traj', rot_unit='deg')

        print('Fusion ARMSE (Rel Trans / Rot): {:.3f} (m) / {:.3f} (a-a)'.format(trans_armse_fusion, rot_armse_fusion))
        print('VO Only ARMSE (Rel Trans / Rot): {:.3f} (m) / {:.3f} (a-a)'.format(trans_armse_vo, rot_armse_vo))

        print('Fusion ARMSE (Traj Trans / Rot): {:.3f} (m) / {:.3f} (a-a)'.format(trans_armse_fusion_traj, rot_armse_fusion_traj))
        print('VO Only ARMSE (Traj Trans / Rot): {:.3f} (m) / {:.3f} (a-a)'.format(trans_armse_vo_traj, rot_armse_vo_traj))

        # # Save to file
        print('Saving to {}'.format(fusion_metrics_file))
        tm_fusion.savemat(fusion_metrics_file)

    # tm_dict = {'VO Only': tm_baseline, 'Fusion': tm_fusion}
    # vis = TrajectoryVisualizer(tm_dict)
    # segs = list(range(100,801,100))
    # vis.plot_topdown(which_plane='xy', outfile=seq + '_topdown.pdf')
    # # vis.plot_cum_norm_err(outfile=seq + '_cum_err.pdf')
    # vis.plot_segment_errors(segs, outfile=seq+'_seg_err.pdf')



if __name__ == '__main__':
    # import cProfile, pstats
    # cProfile.run("run_svo()", "{}.profile".format(__file__))
    # s = pstats.Stats("{}.profile".format(__file__))
    # s.strip_dirs()
    # s.sort_stats("cumtime").print_stats(25)
    np.random.seed(14)
    main()

