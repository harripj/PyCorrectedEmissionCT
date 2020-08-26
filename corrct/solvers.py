#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Solvers for the tomographic reconstruction problem.

@author: Nicola VIGANÒ, Computational Imaging group, CWI, The Netherlands,
and ESRF - The European Synchrotron, Grenoble, France
"""

import numpy as np
import scipy.sparse as sps

from numpy import random as rnd

import time as tm

from . import operators

try:
    import pywt
    has_pywt = True
    use_swtn = pywt.version.version >= '1.0.2'
except ImportError:
    has_pywt = False
    use_swtn = False
    print('WARNING - pywt was not found')


# ---- Regularizers ----


class BaseRegularizer(object):
    """Base regularizer class that defines the Regularizer object interface.
    """

    __reg_name__ = ''

    def __init__(self, weight):
        self.weight = weight

    def upper(self):
        return self.__reg_name__.upper()

    def lower(self):
        return self.__reg_name__.lower()

    def initialize_sigma_tau(self):
        raise NotImplementedError()

    def initialize_dual(self, primal):
        raise NotImplementedError()

    def update_dual(self, dual, primal):
        raise NotImplementedError()

    def apply_proximal(self, dual):
        raise NotImplementedError()

    def compute_update_primal(self, dual):
        raise NotImplementedError()


class Regularizer_TV(BaseRegularizer):
    """Total Variation (TV) regularizer. It can be used to promote piece-wise
    constant reconstructions.
    """

    __reg_name__ = 'TV'

    def __init__(self, weight, ndims=2, axes=None):
        BaseRegularizer.__init__(self, weight=weight)

        if axes is None:
            axes = np.arange(-ndims, 0, dtype=np.int)
        elif not ndims == len(axes):
            print('WARNING - Number of axes different from number of dimensions. Updating dimensions accordingly.')
            ndims = len(axes)
        self.ndims = ndims
        self.axes = axes

        self.D = None

    def initialize_sigma_tau(self):
        self.sigma = 0.5
        return self.weight * 2 * self.ndims

    def initialize_dual(self, primal):
        self.D = operators.TransformGradient(primal.shape, axes=self.axes)
        return np.zeros(self.D.adj_shape, dtype=primal.dtype)

    def update_dual(self, dual, primal):
        dual += self.sigma * self.D(primal)

    def apply_proximal(self, dual):
        dual_dir_norm_l2 = np.linalg.norm(dual, ord=2, axis=0, keepdims=True)
        dual /= np.fmax(1, dual_dir_norm_l2)

    def compute_update_primal(self, dual):
        return self.weight * self.D.T(dual)


class Regularizer_TV2D(Regularizer_TV):
    """Total Variation (TV) regularizer in 2D. It can be used to promote
    piece-wise constant reconstructions.
    """

    __reg_name__ = 'TV2D'

    def __init__(self, weight, axes=None):
        Regularizer_TV.__init__(self, weight=weight, ndims=2, axes=axes)


class Regularizer_TV3D(Regularizer_TV):
    """Total Variation (TV) regularizer in 3D. It can be used to promote
    piece-wise constant reconstructions.
    """

    __reg_name__ = 'TV3D'

    def __init__(self, weight, axes=None):
        Regularizer_TV.__init__(self, weight=weight, ndims=3, axes=axes)


class Regularizer_lap(BaseRegularizer):
    """Laplacian regularizer. It can be used to promote smooth reconstructions.
    """

    __reg_name__ = 'lap'

    def __init__(self, weight, ndims=2, axes=None):
        BaseRegularizer.__init__(self, weight=weight)

        if axes is None:
            axes = np.arange(-ndims, 0, dtype=np.int)
        elif not ndims == len(axes):
            print('WARNING - Number of axes different from number of dimensions. Updating dimensions accordingly.')
            ndims = len(axes)
        self.ndims = ndims
        self.axes = axes

        self.L = None

    def initialize_sigma_tau(self):
        self.sigma = 0.25
        return self.weight * 4 * self.ndims

    def initialize_dual(self, primal):
        self.L = operators.TransformLaplacian(primal.shape, axes=self.axes)
        return np.zeros(self.L.adj_shape, dtype=primal.dtype)

    def update_dual(self, dual, primal):
        dual += self.sigma * self.L(primal)

    def apply_proximal(self, dual):
        dual /= np.fmax(1, np.abs(dual))

    def compute_update_primal(self, dual):
        return self.weight * self.L.T(dual)


class Regularizer_lap2D(Regularizer_lap):
    """Laplacian regularizer in 2D. It can be used to promote smooth
    reconstructions.
    """

    __reg_name__ = 'lap2D'

    def __init__(self, weight):
        Regularizer_lap.__init__(self, weight=weight, ndims=2)


class Regularizer_lap3D(Regularizer_lap):
    """Laplacian regularizer in 3D. It can be used to promote smooth
    reconstructions.
    """

    __reg_name__ = 'lap3D'

    def __init__(self, weight):
        Regularizer_lap.__init__(self, weight=weight, ndims=3)


class Regularizer_l1(BaseRegularizer):
    """l1-norm regularizer. It can be used to promote sparse reconstructions.
    """

    __reg_name__ = 'l1'

    def initialize_sigma_tau(self):
        return self.weight

    def initialize_dual(self, primal):
        return np.zeros(primal.shape, dtype=primal.dtype)

    def update_dual(self, dual, primal):
        dual += primal

    def apply_proximal(self, dual):
        dual /= np.fmax(1, np.abs(dual))

    def compute_update_primal(self, dual):
        return self.weight * dual


class Regularizer_l1wl(BaseRegularizer):
    """l1-norm Wavelet regularizer. It can be used to promote sparse reconstructions.
    """

    __reg_name__ = 'l1wl'

    def __init__(
            self, weight, wavelet, level, ndims=2, axes=None, pad_on_demand='constant', normalized=False):
        if not has_pywt:
            raise ValueError('Cannot use l1wl regularizer because pywavelets is not installed.')
        if not use_swtn:
            raise ValueError('Cannot use l1wl regularizer because pywavelets is too old (<1.0.2).')
        BaseRegularizer.__init__(self, weight=weight)
        self.wavelet = wavelet
        self.level = level
        self.normalized = normalized

        if axes is None:
            axes = np.arange(-ndims, 0, dtype=np.int)
        elif not ndims == len(axes):
            print('WARNING - Number of axes different from number of dimensions. Updating dimensions accordingly.')
            ndims = len(axes)
        self.ndims = ndims
        self.axes = axes

        self.pad_on_demand = pad_on_demand

        self.scaling_func_mult = 2 ** np.arange(self.level, 0, -1)
        self.scaling_func_mult = np.tile(self.scaling_func_mult[:, None], [1, (2 ** self.ndims) - 1])
        self.scaling_func_mult = np.concatenate(([self.scaling_func_mult[0, 0]], self.scaling_func_mult.flatten()))

    def initialize_sigma_tau(self):
        if self.normalized:
            self.sigma = 1
            return self.weight * self.scaling_func_mult.size
        else:
            self.sigma = 1 / self.scaling_func_mult
            tau = np.ones_like(self.scaling_func_mult) * (2 ** self.level - 1)
            tau[0] += 1
            return self.weight * np.sum(tau / self.scaling_func_mult)

    def initialize_dual(self, primal):
        self.H = operators.TransformStationaryWavelet(
            primal.shape, wavelet=self.wavelet, level=self.level, axes=self.axes,
            pad_on_demand=self.pad_on_demand, normalized=self.normalized)
        return np.zeros(self.H.adj_shape, dtype=primal.dtype)

    def update_dual(self, dual, primal):
        upd = self.H(primal)
        if not self.normalized:
            upd *= np.reshape(self.sigma, [-1] + [1] * len(primal.shape))
        dual += upd

    def apply_proximal(self, dual):
        dual /= np.fmax(1, np.abs(dual))

    def compute_update_primal(self, dual):
        return self.weight * self.H.T(dual)


# ---- Data Fidelity terms ----


class DataFidelityBase(object):
    """Base data-fidelity class that defines the object interface.
    """

    __data_fidelity_name__ = ''

    def assign_data(self, data, sigma=1):
        self.data = data
        self.sigma = sigma
        self._compute_sigma_data()

    def _compute_sigma_data(self):
        self.sigma_data = self.sigma * self.data

    def upper(self):
        return self.__data_fidelity_name__.upper()

    def lower(self):
        return self.__data_fidelity_name__.lower()

    def initialize_dual(self):
        return np.zeros_like(self.data)

    def update_dual(self, dual, proj_primal):
        dual += proj_primal * self.sigma

    def apply_proximal(self, dual):
        raise NotImplementedError()

    def compute_update_primal(self, dual):
        return dual


class DataFidelity_l2(DataFidelityBase):
    """l2-norm data-fidelity class.
    """

    __data_fidelity_name__ = 'l2'

    def assign_data(self, data, sigma=1):
        super().assign_data(data=data, sigma=sigma)
        self.sigma1 = 1 / (1 + sigma)

    def apply_proximal(self, dual):
        dual -= self.sigma_data
        dual *= self.sigma1

    def compute_primal_dual_gap(self, proj_primal, dual):
        return (
            (np.linalg.norm(proj_primal - self.data, ord=2) + np.linalg.norm(dual, ord=2)) / 2
            + np.dot(dual.flatten(), self.data.flatten()))


class DataFidelity_wl2(DataFidelity_l2):
    """Weighted l2-norm data-fidelity class.
    """

    __data_fidelity_name__ = 'wl2'

    def __init__(self, weights):
        self.weights = weights

    def assign_data(self, data, sigma=1):
        data = data * self.weights
        sigma = sigma * self.weights
        super().assign_data(data=data, sigma=sigma)

    def compute_update_primal(self, dual):
        return dual * self.weights

    def compute_primal_dual_gap(self, proj_primal, dual):
        return (
            (np.linalg.norm(proj_primal * self.weights - self.data, ord=2) + np.linalg.norm(dual, ord=2)) / 2
            + np.dot(dual.flatten(), self.data.flatten()))


class DataFidelity_l2b(DataFidelity_l2):
    """l2-norm ball data-fidelity class.
    """

    __data_fidelity_name__ = 'l2b'

    def __init__(self, local_error):
        self.local_error = local_error

    def assign_data(self, data, sigma=1):
        self.sigma_error = sigma * self.local_error
        super().assign_data(data=data, sigma=sigma)

    def apply_proximal(self, dual):
        dual -= self.sigma_data
        abs_dual = np.abs(dual)
        valid_dual = abs_dual > 0
        dual[valid_dual] *= np.fmax((abs_dual[valid_dual] - self.sigma_error[valid_dual]) / abs_dual[valid_dual], 0)

    def compute_primal_dual_gap(self, proj_primal, dual):
        return (
            (np.linalg.norm(np.fmax(np.abs(proj_primal - self.data) - self.local_error, 0), ord=2)
             + np.linalg.norm(np.sqrt(self.local_error) * dual, ord=2)) / 2
            + np.dot(dual.flatten(), self.data.flatten()))


class DataFidelity_l1(DataFidelityBase):
    """l1-norm data-fidelity class.
    """

    __data_fidelity_name__ = 'l1'

    def apply_proximal(self, dual):
        dual -= self.sigma_data
        dual /= np.fmax(1, np.abs(dual))

    def compute_primal_dual_gap(self, proj_primal, dual):
        return (
            np.linalg.norm(proj_primal - self.data, ord=1)
            + np.dot(dual.flatten(), self.data.flatten()))


class DataFidelity_KL(DataFidelityBase):
    """KullbackLeibler data-fidelity class.
    """

    __data_fidelity_name__ = 'KL'

    def _compute_sigma_data(self):
        self.sigma_data = 4 * self.sigma * np.fmax(self.data, 0)

    def apply_proximal(self, dual):
        dual[:] = (1 + dual[:] - np.sqrt((dual[:] - 1) ** 2 + self.sigma_data[:])) / 2

    def compute_primal_dual_gap(self, proj_primal, dual):
        return (
            np.linalg.norm(
                proj_primal - self.data * (1 - np.log(self.data) + np.log(np.abs(proj_primal))), ord=1)
            - np.linalg.norm(self.data * np.log(np.abs(1 - dual)), ord=1))


# ---- Solvers ----


class Solver(object):
    """Base solver class.
    """

    def __init__(self, verbose=False, relaxation=1, tolerance=None):
        self.verbose = verbose
        self.relaxation = relaxation
        self.tolerance = tolerance

    def upper(self):
        return type(self).__name__.upper()

    def lower(self):
        return type(self).__name__.lower()

    def _initialize_data_operators(self, A, At):
        if At is None:
            if isinstance(A, np.ndarray):
                At = A.transpose((1, 0))
            elif isinstance(A, sps.dia_matrix) or isinstance(A, sps.linalg.LinearOperator):
                At = A.transpose()

        if isinstance(At, np.ndarray) or isinstance(At, sps.dia_matrix):
            At_m = At
            At = At_m.dot
        if isinstance(A, np.ndarray) or isinstance(A, sps.dia_matrix):
            A_m = A
            A = A_m.dot
        return (A, At)


class Sart(Solver):
    """Solver class implementing the Simultaneous Algebraic Reconstruction
    Technique (SART) algorithm.
    """

    def __call__(  # noqa: C901
            self, A, b, iterations, A_num_rows, x0=None, At=None,
            lower_limit=None, upper_limit=None, x_mask=None, b_mask=None):
        """
        """
        data_type = b.dtype

        c_in = tm.time()

        # Back-projection diagonal re-scaling
        b_ones = np.ones_like(b)
        if b_mask is not None:
            b_ones *= b_mask
        tau = [At(b_ones[ii, :], ii) for ii in range(A_num_rows)]
        tau = np.abs(np.stack(tau, axis=0))
        tau[(tau / np.max(tau)) < 1e-5] = 1
        tau = self.relaxation / tau

        # Forward-projection diagonal re-scaling
        x_ones = np.ones(tau.shape[1:], dtype=data_type)
        if x_mask is not None:
            x_ones *= x_mask
        sigma = [A(x_ones, ii) for ii in range(A_num_rows)]
        sigma = np.abs(np.stack(sigma, axis=0))
        sigma[(sigma / np.max(sigma)) < 1e-5] = 1
        sigma = 1 / sigma

        if x0 is None:
            x0 = np.zeros_like(x_ones)
        x = x0

        if self.tolerance is not None:
            res_norm_0 = np.linalg.norm((b * b_mask).flatten())
            res_norm_rel = np.ones((iterations, )) * self.tolerance
        else:
            res_norm_rel = None

        c_init = tm.time()

        rows_sequence = rnd.permutation(A_num_rows)

        if self.verbose:
            print("- Performing %s iterations (init: %g seconds): " % (
                    self.upper(), c_init - c_in), end='', flush=True)
        for ii in range(iterations):
            if self.verbose:
                prnt_str = "%03d/%03d (avg: %g seconds)" % (
                        ii, iterations, (tm.time() - c_init) / np.fmax(ii, 1))
                print(prnt_str, end='', flush=True)

            for ii_a in rows_sequence:

                res = A(x, ii_a) - b[ii_a, ...]
                if b_mask is not None:
                    res *= b_mask[ii_a, ...]

                x -= At(res * sigma[ii_a, ...], ii_a) * tau[ii_a, ...]

                if lower_limit is not None:
                    x = np.fmax(x, lower_limit)
                if upper_limit is not None:
                    x = np.fmin(x, upper_limit)
                if x_mask is not None:
                    x *= x_mask

            if self.verbose:
                print(('\b') * len(prnt_str), end='', flush=True)
                print((' ') * len(prnt_str), end='', flush=True)
                print(('\b') * len(prnt_str), end='', flush=True)

            if self.tolerance is not None:
                res = np.empty_like(b)
                for ii_a in rows_sequence:
                    res[..., ii_a, :] = A(x, ii_a) - b[..., ii_a, :]
                if b_mask is not None:
                    res *= b_mask
                res_norm_rel[ii] = np.linalg.norm(res) / res_norm_0

                if self.tolerance > res_norm_rel[ii]:
                    break

        if self.verbose:
            print("Done %d in %g seconds." % (iterations, tm.time() - c_in))

        return (x, res_norm_rel)


class Sirt(Solver):
    """Solver class implementing the Simultaneous Iterative Reconstruction
    Technique (SIRT) algorithm.
    """

    def __init__(
            self, verbose=False, tolerance=None, relaxation=1.95,
            regularizer=None):
        Solver.__init__(
            self, verbose=verbose, tolerance=tolerance, relaxation=relaxation)
        self.regularizer = regularizer

    def __call__(  # noqa: C901
            self, A, b, iterations, x0=None, At=None, lower_limit=None,
            upper_limit=None, x_mask=None, b_mask=None):
        """
        """
        (A, At) = self._initialize_data_operators(A, At)

        data_type = b.dtype

        c_in = tm.time()

        # Back-projection diagonal re-scaling
        tau = np.ones(b.shape, data_type)
        if b_mask is not None:
            tau *= b_mask
        tau = np.abs(At(tau))
        if self.regularizer is not None:
            tau += self.regularizer.initialize_sigma_tau()
        tau[(tau / np.max(tau)) < 1e-5] = 1
        tau = self.relaxation / tau

        # Forward-projection diagonal re-scaling
        sigma = np.ones(tau.shape, dtype=data_type)
        if x_mask is not None:
            sigma *= x_mask
        sigma = np.abs(A(sigma))
        sigma[(sigma / np.max(sigma)) < 1e-5] = 1
        sigma = 1 / sigma

        if x0 is None:
            x0 = At(b * sigma) * tau
        x = x0

        if self.tolerance is not None:
            res_norm_0 = np.linalg.norm(b.flatten())
            res_norm_rel = np.ones((iterations, )) * self.tolerance
        else:
            res_norm_rel = None

        c_init = tm.time()

        if self.verbose:
            print("- Performing %s iterations (init: %g seconds): " % (
                    self.upper(), c_init - c_in), end='', flush=True)
        for ii in range(iterations):
            if self.verbose:
                prnt_str = "%03d/%03d (avg: %g seconds)" % (
                        ii, iterations, (tm.time() - c_init) / np.fmax(ii, 1))
                print(prnt_str, end='', flush=True)

            res = b - A(x)
            if b_mask is not None:
                res *= b_mask

            if self.tolerance is not None:
                res_norm_rel[ii] = np.linalg.norm(res.flatten()) / res_norm_0
                if self.tolerance > res_norm_rel[ii]:
                    break

            if self.regularizer is not None:
                q = self.regularizer.initialize_dual(x)
                self.regularizer.update_dual(q, x)
                self.regularizer.apply_proximal(q)

            upd = At(res * sigma)
            if self.regularizer is not None:
                upd -= self.regularizer.compute_update_primal(q)
            x += upd * tau

            if lower_limit is not None:
                x = np.fmax(x, lower_limit)
            if upper_limit is not None:
                x = np.fmin(x, upper_limit)
            if x_mask is not None:
                x *= x_mask

            if self.verbose:
                print(('\b') * len(prnt_str), end='', flush=True)
                print((' ') * len(prnt_str), end='', flush=True)
                print(('\b') * len(prnt_str), end='', flush=True)

        if self.verbose:
            print("Done %d in %g seconds." % (iterations, tm.time() - c_in))

        return (x, res_norm_rel)


class CP(Solver):
    """Solver class implementing the primal-dual algorithm from Chambolle and
    Pock.
    It allows to specify two types of data fidelity terms: l2-norm and
    Kulback-Leibler. The first assumes Gaussian noise and the second Poisson
    noise as dominant sources of noise in the data.
    This solver also allows to specify a chosen regularizer, from the ones
    based on the BaseRegularizer interface.
    """

    def __init__(
            self, verbose=False, tolerance=None, relaxation=0.95,
            data_term='l2', regularizer=None):
        super().__init__(verbose=verbose, tolerance=tolerance, relaxation=relaxation)
        self.data_term = self._initialize_data_fidelity_function(data_term)
        self.regularizer = regularizer

    def _initialize_data_fidelity_function(self, data_term):
        if isinstance(data_term, str):
            if data_term.lower() == 'l2':
                return DataFidelity_l2()
            if data_term.lower() == 'l1':
                return DataFidelity_l1()
            if data_term.lower() == 'kl':
                return DataFidelity_KL()
            else:
                raise ValueError('Unknown data term: "%s", accepted terms are: "l2" | "l2" | "kl".' % data_term)
        else:
            return data_term

    def power_method(self, A, At, b, iterations=5):
        data_type = b.dtype

        x = np.random.rand(*b.shape).astype(data_type)
        x /= np.linalg.norm(x)
        x = At(x)

        x_norm = np.linalg.norm(x)
        L = x_norm

        for ii in range(iterations):
            x /= x_norm
            x = At(A(x))

            x_norm = np.linalg.norm(x)
            L = np.sqrt(x_norm)

        return (L, x.shape)

    def _get_data_sigma_tau_unpreconditioned(self, A, At, b):
        (L, x_shape) = self.power_method(A, At, b)
        tau = L
        if self.regularizer is not None:
            tau += self.regularizer.initialize_sigma_tau()
        tau = self.relaxation / tau
        sigma = 0.95 / L
        return (x_shape, sigma, tau)

    def __call__(  # noqa: C901
            self, A, b, iterations, x0=None, At=None, upper_limit=None,
            lower_limit=None, x_mask=None, b_mask=None, precondition=False):
        """
        """
        (A, At) = self._initialize_data_operators(A, At)
        if precondition:
            try:
                At_abs = At.absolute()
                A_abs = A.absolute()
            except AttributeError:
                print(A, At)
                print('WARNING: Turning off preconditioning because system matrix does not support absolute')
                precondition = False

        data_type = b.dtype

        c_in = tm.time()

        if precondition:
            tau = np.ones(b.shape, data_type)
            if b_mask is not None:
                tau *= b_mask
            tau = np.abs(At_abs(tau))
            if self.regularizer is not None:
                tau += self.regularizer.initialize_sigma_tau()
            tau[(tau / np.max(tau)) < 1e-5] = 1
            tau = self.relaxation / tau

            x_shape = tau.shape

            sigma = np.ones(tau.shape, dtype=data_type)
            if x_mask is not None:
                sigma *= x_mask
            sigma = np.abs(A_abs(sigma))
            sigma[(sigma / np.max(sigma)) < 1e-5] = 1
            sigma = 0.95 / sigma
        else:
            (x_shape, sigma, tau) = self._get_data_sigma_tau_unpreconditioned(A, At, b)

        if x0 is None:
            x0 = np.zeros(x_shape, data_type)
        x = x0
        x_relax = x

        self.data_term.assign_data(b, sigma)
        p = self.data_term.initialize_dual()

        if self.regularizer is not None:
            q = self.regularizer.initialize_dual(x)

        if self.tolerance is not None:
            res_norm_0 = np.linalg.norm(b.flatten())
            res_norm_rel = np.ones((iterations, )) * self.tolerance
        else:
            res_norm_rel = None

        c_init = tm.time()

        if self.verbose:
            reg_info = ''
            if self.regularizer is not None:
                reg_info = '-' + self.regularizer.upper()
            print("- Performing %s-%s%s iterations (init: %g seconds): " % (
                    self.upper(), self.data_term.upper(), reg_info, c_init - c_in), end='', flush=True)
        for ii in range(iterations):
            if self.verbose:
                prnt_str = "%03d/%03d (avg: %g seconds)" % (ii, iterations, (tm.time() - c_init) / np.fmax(ii, 1))
                print(prnt_str, end='', flush=True)

            Ax_rlx = A(x_relax)
            self.data_term.update_dual(p, Ax_rlx)
            self.data_term.apply_proximal(p)

            if b_mask is not None:
                p *= b_mask

            if self.regularizer is not None:
                self.regularizer.update_dual(q, x_relax)
                self.regularizer.apply_proximal(q)

            upd = At(self.data_term.compute_update_primal(p))
            if self.regularizer is not None:
                upd += self.regularizer.compute_update_primal(q)
            x_new = x - upd * tau

            if lower_limit is not None:
                x_new = np.fmax(x_new, lower_limit)
            if upper_limit is not None:
                x_new = np.fmin(x_new, upper_limit)
            if x_mask is not None:
                x_new *= x_mask

            x_relax = x_new + (x_new - x)
            x = x_new

            if self.verbose:
                print(('\b') * len(prnt_str), end='', flush=True)
                print((' ') * len(prnt_str), end='', flush=True)
                print(('\b') * len(prnt_str), end='', flush=True)

            if self.tolerance is not None:
                Ax = A(x)
                res = b - Ax
                res_norm_rel[ii] = np.linalg.norm(res.flatten()) / res_norm_0
                if self.tolerance > res_norm_rel[ii]:
                    break

        if self.verbose:
            print("Done %d in %g seconds." % (iterations, tm.time() - c_in))

        return (x, res_norm_rel)
