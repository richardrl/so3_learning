import pykitti
#import cv2
from matplotlib import pyplot as plt

import numpy as np
from liegroups import SE3, SO3
from pyslam.sensors import StereoCamera
from pyslam.utils import invsqrt
from pyslam.metrics import TrajectoryMetrics
from sparse_stereo_vo_pipeline import SparseStereoPipeline, SparseStereoPipelineParams
from optparse import OptionParser

import copy
import time
import os
import pickle
import csv


def run_sparse_vo(basedir, date, drive, im_range, metrics_filename=None, saved_tracks_filename=None, bad_intrinsics=False):

    #Observation Noise
    obs_var = [1, 1, 2]  # [u,v,d]
    obs_stiffness = invsqrt(np.diagflat(obs_var))

    #Motion Model
    use_const_vel_model = False
    motion_stiffness = invsqrt(np.diagflat(0.05*np.ones(6)))

    #Load data
    dataset = pykitti.raw(basedir, date, drive, frames=im_range, imformat='cv2')
    dataset_len = len(dataset)

    #Setup KITTI Camera parameters
    test_im = next(dataset.cam0)

    #Possibly mess up the intrinsics
    if bad_intrinsics:
        f_err = 50
        c_err = 0 #*np.random.randn(2)
        b_err = 0.1 #*np.random.randn()
        print('Applying BAD intrinsics.')
    else:
        f_err = c_err = b_err = 0.0

    fu = dataset.calib.K_cam0[0, 0] + f_err
    fv = dataset.calib.K_cam0[1, 1] - f_err
    cu = dataset.calib.K_cam0[0, 2] + c_err
    cv = dataset.calib.K_cam0[1, 2] - c_err
    b = dataset.calib.b_gray + b_err

    print('Focal lengths set to: {},{}. (Orig: {}, {})'.format(fu, fv, dataset.calib.K_cam0[0, 0], dataset.calib.K_cam0[1, 1]))
    print('Principal points set to: {},{}. (Orig: {}, {})'.format(cu, cv, dataset.calib.K_cam0[0, 2], dataset.calib.K_cam0[1, 2]))
    print('Baseline set to: {}. (Orig: {})'.format(b, dataset.calib.b_gray))
    


    h, w = test_im.shape
    kitti_camera0 = StereoCamera(cu, cv, fu, fv, b, w, h)

    #Load initial pose and ground truth
    first_oxts = next(dataset.oxts)
    T_cam_imu = SE3.from_matrix(dataset.calib.T_cam0_imu)
    T_cam_imu.normalize()
    T_w_0 = SE3.from_matrix(first_oxts.T_w_imu).dot(T_cam_imu.inv())
    T_w_0.normalize()
    T_w_c_gt = [SE3.from_matrix(o.T_w_imu).dot(T_cam_imu.inv())
        for o in dataset.oxts]

    #Initialize pipeline
    pipeline_params = SparseStereoPipelineParams()
    pipeline_params.camera = kitti_camera0
    pipeline_params.first_pose = T_w_0
    pipeline_params.obs_stiffness = obs_stiffness
    pipeline_params.optimize_trans_only = False
    pipeline_params.use_constant_velocity_motion_model = use_const_vel_model
    pipeline_params.motion_stiffness = motion_stiffness
    pipeline_params.dataset_date_drive = date + '_' + drive
    pipeline_params.saved_stereo_tracks_file = saved_tracks_filename

    svo = SparseStereoPipeline(pipeline_params)
    
    #The magic!
    svo.compute_vo(dataset)    
    
    #Compute statistics
    T_w_c_est = [T for T in svo.T_w_c]
    tm = TrajectoryMetrics(T_w_c_gt, T_w_c_est, convention='Twv')
    # # Save to file
    if metrics_filename:
        print('Saving to {}'.format(metrics_filename))
        tm.savemat(metrics_filename)

    return tm



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

    #Set to none to extract new tracks

    kitti_basedir = '/Users/valentin/Research/KITTI/distorted'
    saved_tracks_dir = '/Users/valentin/Research/KITTI/saved_tracks'
  
    bad_intrinsics = False

    bad_intrinsics_dir = '/Users/valentin/Google Drive/PhD/Projects/Sparse-VO/kitti_results/baseline_bad_intrinsics'
    baseline_dir = '/Users/valentin/Google Drive/PhD/Projects/Sparse-VO/kitti_results/baseline_distorted'

    if bad_intrinsics:
        export_dir = bad_intrinsics_dir
    else:
        export_dir = baseline_dir

    plt.rc('text', usetex=True)
    plt.rc('font', family='serif')

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


    armse_list = []

    compute_seqs = ['05']
    for seq in compute_seqs:

        date = seqs[seq]['date']
        drive = seqs[seq]['drive']
        frames = seqs[seq]['frames']

        print('Odometry sequence {} | {} {}'.format(seq, date, drive))
        metrics_filename = os.path.join(export_dir, date + '_drive_' + drive + '.mat')

        if saved_tracks_dir is None:
            saved_tracks_filename = None
        else:
            saved_tracks_filename = os.path.join(saved_tracks_dir, '{}_{}_frames_{}-{}_saved_tracks.pickle'.format(date, drive, frames[0], frames[-1]))
        
        tm = run_sparse_vo(kitti_basedir, date, drive, frames, metrics_filename, saved_tracks_filename, bad_intrinsics)

        # # Compute errors
        trans_err_norm, rot_err_norm = tm.mean_err(error_type='traj')
        print('Mean Norm Error (Trans / Rot): {:.5f} (m) / {:.5f} (a-a)'.format(trans_err_norm, rot_err_norm))

        if bad_intrinsics:
            baseline_metrics_filename = os.path.join(baseline_dir, date + '_drive_' + drive + '.mat')
            tm_baseline = TrajectoryMetrics.loadmat(baseline_metrics_filename)
            trans_err_norm, rot_err_norm = tm_baseline.mean_err(error_type='traj')
            print('Non-Corrupted Mean Norm Error (Trans / Rot): {:.5f} (m) / {:.5f} (a-a)'.format(trans_err_norm, rot_err_norm))

        # # Make segment error plots
        # outfile = os.path.join(
        #     outdir, date + '_drive_' + drive + '_err.pdf')
        # segs = list(range(100, 801, 100))
        # make_segment_err_plot(tm, segs, outfile)

        # # Make trajectory plots
        # outfile = os.path.join(
        #     outdir, date + '_drive_' + drive + '_traj.pdf')
        # make_topdown_plot(tm, outfile)

        # Save ARMSE values
        #armse_list.append([key, trans_err_norm, rot_err_norm])

    # #Output CSV stats
    # csv_filename = os.path.join(export_dir, 'stats.csv')
    # with open(csv_filename, "w") as f:
    #     writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
    #     writer.writerow(["Seq", "Trans. ARMSE (m)", "Rot. ARMSE (rad)"])
    #     writer.writerows(armse_list)




if __name__ == '__main__':
    # import cProfile, pstats
    # cProfile.run("run_svo()", "{}.profile".format(__file__))
    # s = pstats.Stats("{}.profile".format(__file__))
    # s.strip_dirs()
    # s.sort_stats("cumtime").print_stats(25)
    np.random.seed(14)
    main()

