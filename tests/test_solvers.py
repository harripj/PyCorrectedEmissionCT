#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test `corrct.solvers` package.

@author: Nicola VIGANÒ, Computational Imaging group, CWI, The Netherlands,
and ESRF - The European Synchrotron, Grenoble, France
"""

import numpy as np

import unittest

from corrct import projectors
from corrct import solvers
from corrct import utils_proc


eps = np.finfo(np.float32).eps


class TestSolvers(unittest.TestCase):
    """Tests for the solvers in `corrct.solvers` package."""

    __oversize_data = 5

    def setUp(self):
        """Set up test fixtures, if any."""
        self.test_vols_shape = (10, 10)
        self.test_prjs_shape = (self.__oversize_data, np.prod(self.test_vols_shape))

        self.vol_rand_2d = np.fmin(np.random.rand(*self.test_vols_shape[:2]) + eps, 1)
        self.vol_flat_2d = utils_proc.get_circular_mask(self.test_vols_shape[:2], -2)

        self.proj_matrix_2d = (np.random.rand(np.prod(self.test_prjs_shape), np.prod(self.test_vols_shape)) > 0.5).astype(
            np.float32
        )

        self.data_rand_2d = self.fwd_op(self.proj_matrix_2d, self.vol_rand_2d, self.test_prjs_shape)

        self.data_flat_2d = self.fwd_op(self.proj_matrix_2d, self.vol_flat_2d, self.test_prjs_shape)
        self.data_flat_2d += np.random.randn(*self.data_flat_2d.shape) * 1e-3

        self.tolerance = 1e-2

    def tearDown(self):
        """Tear down test fixtures, if any."""

    def fwd_op(self, M, x, y_shape):
        return np.dot(M, x.flatten()).reshape(y_shape)

    def bwd_op(self, M, y, x_shape):
        return np.dot(y.flatten(), M).reshape(x_shape)

    def get_A_At(self, vol_dims):
        if vol_dims.lower() == "2d":

            def A(x):
                return self.fwd_op(self.proj_matrix_2d, x, self.test_prjs_shape)

            def At(y):
                return self.bwd_op(self.proj_matrix_2d, y, self.test_vols_shape[:2])

        else:
            raise ValueError("Only 2D implemented.")
        return (A, At)

    def test_000_SIRT(self):
        """Test SIRT algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        algo = solvers.Sirt()
        sol, _ = algo(A, self.data_rand_2d, 500)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_rand_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_rand_2d, atol=self.tolerance))

    def test_001_PDHG_LS(self):
        """Test Chambolle-Pock least-squares algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        algo = solvers.PDHG()
        sol, _ = algo(A, self.data_rand_2d, 500)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_rand_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_rand_2d, atol=self.tolerance))

    def test_002_SIRT_TV(self):
        """Test SIRT TV-min algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        reg = solvers.Regularizer_TV2D(1e-4)
        algo = solvers.Sirt(regularizer=reg)
        sol, _ = algo(A, self.data_flat_2d, 2500)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_flat_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_flat_2d, atol=self.tolerance))

    def test_003_PDHG_LS_TV(self):
        """Test Chambolle-Pock unconstrained least-squares TV-min algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        reg = solvers.Regularizer_TV2D(1e-4)
        algo = solvers.PDHG(regularizer=reg)
        sol, _ = algo(A, self.data_flat_2d, 500)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_flat_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_flat_2d, atol=self.tolerance))

    def test_004_PDHG_LS_TV_unconstrained(self):
        """Test Chambolle-Pock unconstrained least-squares TV-min algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        reg = solvers.Regularizer_TV2D(1e-4)
        algo = solvers.PDHG(regularizer=reg)
        sol, _ = algo(A, self.data_flat_2d, 500)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_flat_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_flat_2d, atol=self.tolerance))

    def test_005_PDHG_LS_TV_constrained01(self):
        """Test Chambolle-Pock constrained [0, 1] least-squares TV-min algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        reg = solvers.Regularizer_TV2D(1e-4)
        algo = solvers.PDHG(regularizer=reg)
        sol, _ = algo(A, self.data_flat_2d, 500, lower_limit=0, upper_limit=1)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_flat_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_flat_2d, atol=self.tolerance))

    def test_006_PDHG_LS_TV_unconstrained_no_precond(self):
        """Test Chambolle-Pock not preconditioned, unconstrained least-squares TV-min algorithm in 2D."""

        A = projectors.ProjectorMatrix(self.proj_matrix_2d, self.test_vols_shape, self.test_prjs_shape)
        reg = solvers.Regularizer_TV2D(1e-4)
        algo = solvers.PDHG(regularizer=reg)
        sol, _ = algo(A, self.data_flat_2d, 1000, precondition=False)

        print("Max absolute deviation is: {}. ".format(np.max(np.abs(self.vol_flat_2d - sol))), end="", flush=True)
        assert np.all(np.isclose(sol, self.vol_flat_2d, atol=self.tolerance))
