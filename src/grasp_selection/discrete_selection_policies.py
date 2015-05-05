"""
Policies for selecting the next point in discrete solvers

Author: Jeff Mahler
"""
from abc import ABCMeta, abstractmethod

import logging
import numpy as np
import scipy.io

import models
import IPython

class DiscreteSelectionPolicy:
    __metaclass__ = ABCMeta

    def __init__(self, model = None):
        self.model_ = model

    @abstractmethod
    def choose_next(self):
        """
        Choose the next index of the model to sample 
        """
        pass

    def set_model(self, model):
        if not isinstance(model, models.DiscreteModel):
            raise ValueError('Must supply a discrete predictive model')
        self.model_ = model

class UniformSelectionPolicy(DiscreteSelectionPolicy):
    def choose_next(self):
        """ Returns an index uniformly at random"""
        if self.model_ is None:
            raise ValueError('Must set predictive model')
        num_vars = self.model_.num_vars()
        next_index = np.random.choice(num_vars)
        return next_index

class MaxDiscreteSelectionPolicy(DiscreteSelectionPolicy):
    def choose_next(self):
        """ Returns the index of the maximal variable, breaking ties uniformly at random"""
        if self.model_ is None:
            raise ValueError('Must set predictive model')
        max_indices, max_mean_vals, max_var_vals = self.model_.max_prediction()
        num_max_indices = max_indices.shape[0]
        next_index = np.random.choice(num_max_indices)
        return max_indices[next_index]

class ThompsonSelectionPolicy(DiscreteSelectionPolicy):
    """ Chooses the next point using the Thompson sampling selection policy"""
    def choose_next(self, stop = False):
        """ Returns the index of the maximal random sample, breaking ties uniformly at random"""
        if self.model_ is None:
            raise ValueError('Must set predictive model')
        sampled_values = self.model_.sample()
        if stop:
            IPython.embed()
        max_indices = np.where(sampled_values == np.max(sampled_values))[0]
        num_max_indices = max_indices.shape[0]
        next_index = np.random.choice(num_max_indices)
        return max_indices[next_index]        

class BetaBernoulliGittinsIndex98Policy(DiscreteSelectionPolicy):
    """ Chooses the next point using the BetaBernoulli gittins index policy with gamma = 0.98"""
    def __init__(self, model = None):
        self.indices_ = scipy.io.loadmat('data/bandits/gittins_indices_98.mat')
        self.indices_ = self.indices_['indices']
        DiscreteSelectionPolicy.__init__(self, model)

    def choose_next(self):
        """ Returns the index of the maximal random sample, breaking ties uniformly at random"""
        if self.model_ is None:
            raise ValueError('Must set predictive model')
        if not isinstance(self.model_, models.BetaBernoulliModel):
            raise ValueError('Gittins index policy can only be used with Beta-bernoulli models')
        
        alphas = self.model_.posterior_alphas.astype(np.uint64)
        betas = self.model_.posterior_betas.astype(np.uint64)

        # subtract one, since the indices are intended for matlab 1 indexing
        alphas = alphas - 1
        betas = betas - 1

        # snap alphas and betas to boundaries of index matrix
        alphas[alphas >= self.indices_.shape[0]] = self.indices_.shape[0] - 1
        betas[betas >= self.indices_.shape[1]] = self.indices_.shape[1] - 1

        # find maximum of gittins indices
        gittins_indices = self.indices_[alphas, betas]

        max_indices = np.where(gittins_indices == np.max(gittins_indices))[0]
#        IPython.embed()
        num_max_indices = max_indices.shape[0]
        next_index = np.random.choice(num_max_indices)
        return max_indices[next_index]        