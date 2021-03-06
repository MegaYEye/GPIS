B"""
Main file for correlated bandit experiments.

Author: Brian Hou
"""
import logging
import pickle as pkl
import os
import random
import string
import time

import IPython
import json_serialization as jsons
import matplotlib.pyplot as plt
import numpy as np
import scipy.spatial.distance as ssd
import scipy.stats

import antipodal_grasp_sampler as ags
import database as db
import discrete_adaptive_samplers as das
import experiment_config as ec
import feature_functions as ff
import grasp as g
import grasp_sampler as gs
import json_serialization as jsons
import kernels
import models
import objectives
import quality as q
import pfc
import pr2_grasp_checker as pgc
import termination_conditions as tc

def experiment_hash(N = 10):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(N))

class BanditCorrelatedExperimentResult:
    def __init__(self, ua_reward, ts_reward, ts_corr_reward, ua_result, ts_result, ts_corr_result, obj_key = '', num_objects = 1):
        self.ua_reward = ua_reward
        self.ts_reward = ts_reward
        self.ts_corr_reward = ts_corr_reward

        self.ua_result = ua_result
        self.ts_result = ts_result
        self.ts_corr_result = ts_corr_result

        self.obj_key = obj_key
        self.num_objects = num_objects

    def save(self, out_dir):
        """ Save this object to a pickle file in specified dir """
        out_filename = os.path.join(out_dir, self.obj_key + '.pkl')
        with open(out_filename, 'w') as f:
            pkl.dump(self, f)

    @staticmethod
    def compile_results(result_list):
        """ Put all results in a giant list """
        if len(result_list) == 0:
            return None

        ua_reward = np.zeros([len(result_list), result_list[0].ua_reward.shape[0]])
        ts_reward = np.zeros([len(result_list), result_list[0].ts_reward.shape[0]])
        ts_corr_reward = np.zeros([len(result_list), result_list[0].ts_corr_reward.shape[0]])

        i = 0
        obj_keys = []
        for r in result_list:
            ua_reward[i,:] = r.ua_reward
            ts_reward[i,:] = r.ts_reward
            ts_corr_reward[i,:] = r.ts_corr_reward
            obj_keys.append(r.obj_key)
            i = i + 1

        ua_results = [r.ua_result for r in result_list]
        ts_results = [r.ts_result for r in result_list]
        ts_corr_results = [r.ts_corr_result for r in result_list]

        return BanditCorrelatedExperimentResult(ua_reward, ts_reward, ts_corr_reward,
                                                ua_results,
                                                ts_results,
                                                ts_corr_results,
                                                obj_keys,
                                                len(result_list))

def reward_vs_iters(result, true_pfc, plot=False, normalize=True):
    """Computes the expected values for the best arms of a BetaBernoulliModel at
    each time step.
    Params:
        result - AdaptiveSamplingResult instance, from a BetaBernoulliModel
        normalize - Divide by true best value
    Returns:
        best_values - list of floats, expected values over time
    """
    true_best_value = np.max(true_pfc)
    best_pred_values = [true_pfc[m.best_pred_ind] for m in result.models]
    if normalize:
        best_pred_values = best_pred_values / true_best_value

    if plot:
        plt.figure()
        plt.plot(result.iters, best_pred_values, color='blue', linewidth=2)
        plt.xlabel('Iteration')
        plt.ylabel('P(Success)')

    return best_pred_values

def save_grasps(grasps, pfcs, obj, dest):
    i = 0
    for grasp, pfc in zip(grasps, pfcs):
        grasp_json = grasp.to_json(quality=pfc, method='PFC')
        grasp_filename = os.path.join(dest, obj.key + '_' + str(i) + '.json')
        with open(grasp_filename, 'w') as grasp_file:
            jsons.dump(grasp_json, grasp_file)
        i += 1

def load_grasps(obj, source):
    grasps = []
    for root, dirs, files in os.walk(source):
        for f in files:
            if f.find(obj.key) != -1 and f.endswith('.json'):
                filename = os.path.join(root, f)
                with open(filename, 'r') as grasp_file:
                    grasps.append(g.ParallelJawPtGrasp3D.from_json(jsons.load(grasp_file)))
    return grasps

def label_correlated(obj, chunk, dest, config, plot=False, load=True):
    """Label an object with grasps according to probability of force closure,
    using correlated bandits."""
    bandit_start = time.clock()

    np.random.seed(100)
    chunk = db.Chunk(config)

    if not load:
        # load grasps from database
        sample_start = time.clock()
                              
        if config['grasp_sampler'] == 'antipodal':
            logging.info('Using antipodal grasp sampling')
            sampler = ags.AntipodalGraspSampler(config)
            grasps = sampler.generate_grasps(obj, check_collisions=config['check_collisions'], vis=plot)

            # pad with gaussian grasps
            num_grasps = len(grasps)
            min_num_grasps = config['min_num_grasps']
            if num_grasps < min_num_grasps:
                target_num_grasps = min_num_grasps - num_grasps
                gaussian_sampler = gs.GaussianGraspSampler(config)        
                gaussian_grasps = gaussian_sampler.generate_grasps(obj, target_num_grasps=target_num_grasps,
                                                                   check_collisions=config['check_collisions'], vis=plot)
                grasps.extend(gaussian_grasps)
        else:
            logging.info('Using Gaussian grasp sampling')
            sampler = gs.GaussianGraspSampler(config)        
            grasps = sampler.generate_grasps(obj, check_collisions=config['check_collisions'], vis=plot,
                                             grasp_gen_mult = 6)
        sample_end = time.clock()
        sample_duration = sample_end - sample_start
        logging.info('Loaded %d grasps' %(len(grasps)))
        logging.info('Grasp candidate loading took %f sec' %(sample_duration))

        if not grasps:
            logging.info('Skipping %s' %(obj.key))
            return None

    else:
        grasps = load_grasps(obj, dest)
        grasps = grasps[:20]
#        grasps = chunk.load_grasps(obj.key)

    # load features for all grasps
    feature_start = time.clock()
    feature_extractor = ff.GraspableFeatureExtractor(obj, config)

    features = feature_extractor.compute_all_features(grasps)
    """
    if not load:
        features = feature_extractor.compute_all_features(grasps)
    else:
        feature_loader = ff.GraspableFeatureLoader(obj, chunk.name, config)
        features = feature_loader.load_all_features(grasps) # in same order as grasps
    """
    feature_end = time.clock()
    feature_duration = feature_end - feature_start
    logging.info('Loaded %d features' %(len(features)))
    logging.info('Grasp feature loading took %f sec' %(feature_duration))

    # prune crappy grasps
    all_features = []
    all_grasps = []
    for grasp, feature in zip(grasps, features):
        if feature is not None:
            all_grasps.append(grasp)
            all_features.append(feature)
    grasps = all_grasps

    # compute distances for debugging
    distances = np.zeros([len(grasps), len(grasps)])
    i = 0
    for feature_i in all_features:
        j = 0
        for feature_j in all_features:
            distances[i,j] = np.linalg.norm(feature_i.phi - feature_j.phi)
            j += 1
        i += 1

    # bandit params
    brute_force_iter = config['bandit_brute_force_iter']
    max_iter = config['bandit_max_iter']
    confidence = config['bandit_confidence']
    snapshot_rate = config['bandit_snapshot_rate']
    tc_list = [
        tc.MaxIterTerminationCondition(max_iter),
        ]

    # run bandits!
    graspable_rv = pfc.GraspableObjectGaussianPose(obj, config)
    f_rv = scipy.stats.norm(config['friction_coef'], config['sigma_mu']) # friction Gaussian RV

    candidates = []
    for grasp, features in zip(grasps, all_features):
        logging.info('Adding grasp %d' %len(candidates))
        grasp_rv = pfc.ParallelJawGraspGaussian(grasp, config)
        pfc_rv = pfc.ForceClosureRV(grasp_rv, graspable_rv, f_rv, config)
        if features is None:
            logging.info('Could not compute features for grasp.')
        else:
            pfc_rv.set_features(features)
            candidates.append(pfc_rv)

    # feature transform
    def phi(rv):
        return rv.features

    nn = kernels.KDTree(phi=phi)
    kernel = kernels.SquaredExponentialKernel(
        sigma=config['kernel_sigma'], l=config['kernel_l'], phi=phi)
    objective = objectives.RandomBinaryObjective()

    if not load:
        # uniform allocation for true values
        ua = das.UniformAllocationMean(objective, candidates)
        logging.info('Running uniform allocation for true pfc.')
        ua_result = ua.solve(termination_condition=tc.MaxIterTerminationCondition(brute_force_iter),
                             snapshot_rate=snapshot_rate)
        estimated_pfc = models.BetaBernoulliModel.beta_mean(ua_result.models[-1].alphas, ua_result.models[-1].betas)

        save_grasps(grasps, estimated_pfc, obj, dest)

        # plot params
        line_width = config['line_width']
        font_size = config['font_size']
        dpi = config['dpi']

        # plot histograms
        num_bins = 100
        bin_edges = np.linspace(0, 1, num_bins+1)
        plt.figure()
        n, bins, patches = plt.hist(estimated_pfc, bin_edges)
        plt.xlabel('Probability of Success', fontsize=font_size)
        plt.ylabel('Num Grasps', fontsize=font_size)
        plt.title('Histogram of Grasps by Probability of Success', fontsize=font_size)
        plt.show()

        exit(0)
    else:
        estimated_pfc = np.array([g.quality for g in grasps])
        
    # debugging for examining bad features
    bad_i = 0
    bad_j = 1
    grasp_i = grasps[bad_i]
    grasp_j = grasps[bad_j]
    pfc_i = estimated_pfc[bad_i]
    pfc_j = estimated_pfc[bad_j]
    features_i = all_features[bad_i]
    features_j = all_features[bad_j]
    feature_sq_diff = (features_i.phi - features_j.phi)**2
#    grasp_i.close_fingers(obj, vis=True)
#    grasp_j.close_fingers(obj, vis=True)

    grasp_i.surface_information(obj, config['window_width'], config['window_steps'])
    grasp_j.surface_information(obj, config['window_width'], config['window_steps'])

    w = config['window_steps']
    wi1 = np.reshape(features_i.extractors_[0].extractors_[1].phi, [w, w]) 
    wi2 = np.reshape(features_i.extractors_[1].extractors_[1].phi, [w, w]) 
    wj1 = np.reshape(features_j.extractors_[0].extractors_[1].phi, [w, w]) 
    wj2 = np.reshape(features_j.extractors_[1].extractors_[1].phi, [w, w]) 

    a = 0.1
    plt.figure()
    plt.subplot(2,2,1)
    plt.imshow(wi1, cmap=plt.cm.Greys, interpolation='none')
    plt.colorbar()
    plt.clim(-a, a) # fixing color range for visual comparisons            
    plt.title('wi1')

    plt.subplot(2,2,2)
    plt.imshow(wi2, cmap=plt.cm.Greys, interpolation='none')
    plt.colorbar()
    plt.clim(-a, a) # fixing color range for visual comparisons            
    plt.title('wi2')

    plt.subplot(2,2,3)
    plt.imshow(wj1, cmap=plt.cm.Greys, interpolation='none')
    plt.colorbar()
    plt.clim(-a, a) # fixing color range for visual comparisons            
    plt.title('wj1')

    plt.subplot(2,2,4)
    plt.imshow(wj2, cmap=plt.cm.Greys, interpolation='none')
    plt.colorbar()
    plt.clim(-a, a) # fixing color range for visual comparisons            
    plt.title('wj2')

#    plt.show()
#    IPython.embed()

    num_trials = config['num_trials']
    ts_rewards = []
    ts_corr_rewards = []

    for t in range(num_trials):
        logging.info('Trial %d' %(t))

        # Thompson sampling
        ts = das.ThompsonSampling(objective, candidates)
        logging.info('Running Thompson sampling.')
        ts_result = ts.solve(termination_condition=tc.OrTerminationCondition(tc_list), snapshot_rate=snapshot_rate)

        # correlated Thompson sampling for even faster convergence
        ts_corr = das.CorrelatedThompsonSampling(
            objective, candidates, nn, kernel, tolerance=config['kernel_tolerance'])
        logging.info('Running correlated Thompson sampling.')
        ts_corr_result = ts_corr.solve(termination_condition=tc.OrTerminationCondition(tc_list), snapshot_rate=snapshot_rate)

        ts_normalized_reward = reward_vs_iters(ts_result, estimated_pfc)
        ts_corr_normalized_reward = reward_vs_iters(ts_corr_result, estimated_pfc)
        
        ts_rewards.append(ts_normalized_reward)
        ts_corr_rewards.append(ts_corr_normalized_reward)

    # get the bandit rewards
    all_ts_rewards = np.array(ts_rewards)
    all_ts_corr_rewards = np.array(ts_corr_rewards)
    avg_ts_rewards = np.mean(all_ts_rewards, axis=0)
    avg_ts_corr_rewards = np.mean(all_ts_corr_rewards, axis=0)

    # get correlations and plot
    k = kernel.matrix(candidates)
    k_vec = k.ravel()
    pfc_arr = np.array([estimated_pfc]).T
    pfc_diff = ssd.squareform(ssd.pdist(pfc_arr))
    pfc_vec = pfc_diff.ravel()

    bad_ind = np.where(pfc_diff > 1.0 - k) 

    plt.figure()
    plt.scatter(k_vec, pfc_vec)
    plt.xlabel('Kernel', fontsize=15)
    plt.ylabel('PFC Diff', fontsize=15)
    plt.title('Correlations', fontsize=15)
#    plt.show()

#    IPython.embed()

    # plot params
    line_width = config['line_width']
    font_size = config['font_size']
    dpi = config['dpi']

    # plot histograms
    num_bins = 100
    bin_edges = np.linspace(0, 1, num_bins+1)
    plt.figure()
    n, bins, patches = plt.hist(estimated_pfc, bin_edges)
    plt.xlabel('Probability of Success', fontsize=font_size)
    plt.ylabel('Num Grasps', fontsize=font_size)
    plt.title('Histogram of Grasps by Probability of Success', fontsize=font_size)

    # plot the results
    plt.figure()
    plt.plot(ts_result.iters, avg_ts_rewards, c=u'g', linewidth=line_width, label='Thompson Sampling (Uncorrelated)')
    plt.plot(ts_corr_result.iters, avg_ts_corr_rewards, c=u'r', linewidth=line_width, label='Thompson Sampling (Correlated)')

    plt.xlim(0, np.max(ts_result.iters))
    plt.ylim(0.5, 1)
    plt.xlabel('Iteration', fontsize=font_size)
    plt.ylabel('Normalized Probability of Force Closure', fontsize=font_size)
    plt.title('Avg Normalized PFC vs Iteration', fontsize=font_size)

    handles, labels = plt.gca().get_legend_handles_labels()
    plt.legend(handles, labels, loc='lower right')
    plt.show()

    IPython.embed()
        
    """
    # aggregate grasps
    object_grasps = [candidates[i].grasp for i in ts_result.best_candidates]
    grasp_qualities = list(ts_result.best_pred_means)

    bandit_stop = time.clock()
    logging.info('Bandits took %f sec' %(bandit_stop - bandit_start))

    # get rotated, translated versions of grasps
    delay = 0
    pr2_grasps = []
    pr2_grasp_qualities = []
    theta_res = config['grasp_theta_res'] * np.pi
#    grasp_checker = pgc.OpenRaveGraspChecker(view=config['vis_grasps'])

    if config['vis_grasps']:
        delay = config['vis_delay']

    for grasp, grasp_quality in zip(object_grasps, grasp_qualities):
        rotated_grasps = grasp.transform(obj.tf, theta_res)
#        rotated_grasps = grasp_checker.prune_grasps_in_collision(obj, rotated_grasps, auto_step=True, close_fingers=False, delay=delay)
        pr2_grasps.extend(rotated_grasps)
        pr2_grasp_qualities.extend([grasp_quality] * len(rotated_grasps))

    logging.info('Num grasps: %d' %(len(pr2_grasps)))

    grasp_filename = os.path.join(dest, obj.key + '.json')
    with open(grasp_filename, 'w') as f:
        jsons.dump([g.to_json(quality=q) for g, q in
                   zip(pr2_grasps, pr2_grasp_qualities)], f)

    ua_normalized_reward = reward_vs_iters(ua_result, estimated_pfc)
    ts_normalized_reward = reward_vs_iters(ts_result, estimated_pfc)
    ts_corr_normalized_reward = reward_vs_iters(ts_corr_result, estimated_pfc)

    return BanditCorrelatedExperimentResult(ua_normalized_reward, ts_normalized_reward, ts_corr_normalized_reward,
                                            ua_result, ts_result, ts_corr_result, obj_key=obj.key)
                                            """
    return None

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('config', default='cfg/correlated.yaml')
    parser.add_argument('output_dest', default='out/')
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.INFO)

    # read config file
    config = ec.ExperimentConfig(args.config)
    chunk = db.Chunk(config)

    # make output directory
    dest = os.path.join(args.output_dest, chunk.name)
    try:
        os.makedirs(dest)
    except os.error:
        pass

    # loop through objects, labelling each
    results = []
    avg_experiment_result = None
    for obj in chunk:
        logging.info('Labelling object {}'.format(obj.key))
        experiment_result = label_correlated(obj, chunk, dest, config)
        if experiment_result is None:
            continue # no grasps to run bandits on for this object
        results.append(experiment_result)

    if len(results) == 0:
        logging.info('Exiting. No grasps found')
        exit(0)

    # combine results
    all_results = BanditCorrelatedExperimentResult.compile_results(results)

    # plotting of final results
    ua_normalized_reward = np.mean(all_results.ua_reward, axis=0)
    ts_normalized_reward = np.mean(all_results.ts_reward, axis=0)
    ts_corr_normalized_reward = np.mean(all_results.ts_corr_reward, axis=0)

    if config['plot']:
        plt.figure()
        ua_obj = plt.plot(all_results.ua_result[0].iters, ua_normalized_reward,
                          c=u'b', linewidth=2.0, label='Uniform Allocation')
        ts_obj = plt.plot(all_results.ts_result[0].iters, ts_normalized_reward,
                          c=u'g', linewidth=2.0, label='Thompson Sampling (Uncorrelated)')
        ts_corr_obj = plt.plot(all_results.ts_corr_result[0].iters, ts_corr_normalized_reward,
                          c=u'r', linewidth=2.0, label='Thompson Sampling (Correlated)')
        plt.xlim(0, np.max(all_results.ts_result[0].iters))
        plt.ylim(0.5, 1)
        plt.legend(loc='lower right')
        plt.show()

    # save to file
    logging.info('Saving results to %s' %(dest))
    for r in results:
        r.save(dest)
