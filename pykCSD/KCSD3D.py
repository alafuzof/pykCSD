# -*- coding: utf-8 -*-
from __future__ import division

import numpy as np
from numpy import dot, identity
from numpy.linalg import norm, inv
import scipy.spatial.distance as distance

import cross_validation as cv
import basis_functions as bf
import source_distribution as sd
import potentials as pt
import dist_table_utils as dt
import plotting_utils as plut


class KCSD3D(object):
    """
    3D variant of the kCSD method.
    It assumes sources are distributed in 3D space.
    """

    def __init__(self, elec_pos, sampled_pots, params={}):
        """
        Parameters
        ----------
            elec_pos : numpy array
                positions of electrodes
            sampled_pots : numpy array
                potentials measured by electrodes
            params : set, optional
                configuration parameters, that may contain the following keys:
                    'sigma' : float
                        space conductance of the medium
                    'n_sources' : int
                        number of sources
                    'source_type' : str
                        basis function type ('gauss', 'step', 'gauss_lim')
                    'R_init' : float
                        demanded thickness of the basis element
                    'h' : float
                        cylinder radius
                    'dist_density' : int
                        resolution of the dist_table
                    'x_min', 'x_max', 'y_min', 'y_max' : floats
                        boundaries for CSD estimation space
                    'ext' : float
                        length of space extension: x_min-ext ... x_max+ext
                    'gdX', 'gdY' : float
                        space increments in the estimation space
                    'cross_validation' : str
                        type of index generator
                    'lambd' : float
                        regularization parameter for ridge regression
        """
        self.validate_parameters(elec_pos, sampled_pots)
        self.elec_pos = elec_pos
        self.sampled_pots = sampled_pots
        self.set_parameters(params)

    def validate_parameters(self, elec_pos, sampled_pots):
        if elec_pos.shape[0] != sampled_pots.shape[0]:
            raise Exception("Number of measured potentials is not equal \
                             to electrode number!")
        if elec_pos.shape[0] < 4:
            raise Exception("Number of electrodes must be at least 4!")

    def set_parameters(self, params):
        self.sigma = params.get('sigma', 1.0)
        self.n_sources = params.get('n_sources', 100)
        self.xmax = params.get('x_max', np.max(self.elec_pos[:, 0]))
        self.xmin = params.get('x_min', np.min(self.elec_pos[:, 0]))
        self.ymax = params.get('y_max', np.max(self.elec_pos[:, 1]))
        self.ymin = params.get('y_min', np.min(self.elec_pos[:, 1]))
        self.zmax = params.get('z_max', np.max(self.elec_pos[:, 2]))
        self.zmin = params.get('z_min', np.min(self.elec_pos[:, 2]))

        self.lambd = params.get('lambda', 0.0)
        self.R_init = params.get('R_init',
                                 2 * distance.pdist(self.elec_pos).min())
        self.h = params.get('h', 1.0)
        self.ext_X = params.get('ext_X', 0.0)
        self.ext_Y = params.get('ext_Y', 0.0)
        self.ext_Z = params.get('ext_Z', 0.0)

        self.gdX = params.get('gdX', 0.05 * (self.xmax - self.xmin))
        self.gdY = params.get('gdY', 0.05 * (self.ymax - self.ymin))
        self.gdZ = params.get('gdZ', 0.05 * (self.zmax - self.zmin))
        self.dist_table_density = 100

        self.source_type = params.get('source_type', 'gauss')
        basis_types = {
            "step": bf.step_rescale_3D,
            "gauss": bf.gauss_rescale_3D,
            "gauss_lim": bf.gauss_rescale_lim_3D,
        }
        if self.source_type not in basis_types.keys():
            raise Exception("Incorrect source type!")
        else:
            self.basis = basis_types.get(self.source_type)

        self.lambdas = np.array([1.0/2**n for n in xrange(0, 20)])

        nx = (self.xmax - self.xmin)/self.gdX + 1
        ny = (self.ymax - self.ymin)/self.gdY + 1
        nz = (self.zmax - self.zmin)/self.gdZ + 1
        lin_x = np.linspace(self.xmin, self.xmax, nx)
        lin_y = np.linspace(self.ymin, self.ymax, ny)
        lin_z = np.linspace(self.zmin, self.ymax, nz)
        self.space_X, self.space_Y, self.space_Z = np.meshgrid(lin_x,
                                                               lin_y,
                                                               lin_z)

        (self.X_src, self.Y_src, self.Z_src, self.R) = sd.make_src_3D(
            self.space_X, self.space_Y, self.space_Z,
            self.n_sources,
            self.ext_X, self.ext_Y, self.ext_Z,
            self.R_init
        )

        Lx = np.max(self.X_src) - np.min(self.X_src) + self.R
        Ly = np.max(self.Y_src) - np.min(self.Y_src) + self.R
        Lz = np.max(self.Z_src) - np.min(self.Z_src) + self.R
        self.dist_max = (Lx**2 + Ly**2 + Lz**2)**0.5

    def estimate_pots(self):
        """Calculates Local Field Potentials."""
        estimation_table = self.interp_pot

        k_inv = inv(self.k_pot + self.lambd * identity(self.k_pot.shape[0]))
        beta = dot(k_inv, self.sampled_pots)

        (nx, ny, nz) = self.space_X.shape
        output = np.zeros(nx * ny * nz)

        for i in xrange(self.elec_pos.shape[0]):
            output[:] += beta[i]*estimation_table[:, i]

        self.estimated_pots = output.reshape(nx, ny, nz)
        return self.estimated_pots

    def estimate_csd(self):
        """Calculates Current Source Density."""
        estimation_table = self.k_interp_cross

        k_inv = inv(self.k_pot + self.lambd * identity(self.k_pot.shape[0]))
        beta = dot(k_inv, self.sampled_pots)

        (nx, ny, nz) = self.space_X.shape
        output = np.zeros(nx * ny * nz)

        for i in xrange(self.elec_pos.shape[0]):
            output[:] += beta[i] * estimation_table[:, i]

        self.estimated_csd = output.reshape(nx, ny, nz)
        return self.estimated_csd

    def save(self, filename='result'):
        """Save results to file."""
        pass

    def __repr__(self):
        info = ''.join(self.__class__.__name__)
        for key in vars(self).keys():
            if not key.startswith('_'):
                info += '%s : %s\n' % (key, vars(self)[key])
        return info

    def plot_all(self):
        extent = [self.xmin, self.xmax,
                  self.ymin, self.ymax,
                  self.zmin, self.zmax]
        plut.plot_3D(self.elec_pos, self.estimated_pots,
                     self.estimated_csd, extent)

    #
    # subfunctions
    #

    def calculate_matrices(self):
        """
        Prepares all the required matrices to calculate CSD and potentials.
        """
        self.create_dist_table()

        self.calculate_b_pot_matrix()
        self.k_pot = dot(self.b_pot_matrix.T, self.b_pot_matrix)

        self.calculate_b_src_matrix()
        self.k_interp_cross = dot(self.b_src_matrix, self.b_pot_matrix)

        self.calculate_b_interp_pot_matrix()
        self.interp_pot = dot(self.b_interp_pot_matrix, self.b_pot_matrix)

    def create_dist_table(self):
        """
        Create table of a single source base element contribution
        to overall potential as a function of distance.
        The last record corresponds to the distance equal to the
        diagonal of the cuboid.
        """
        xs = dt.probe_dist_table_points(self.R, self.dist_max,
                                        self.dist_table_density)
        dist_table = np.zeros(len(xs))

        for i, x in enumerate(xs):
            pos = (x/self.dist_table_density) * self.dist_max
            dist_table[i] = pt.b_pot_3d_mc(pos, self.R, self.h, self.sigma,
                                           self.basis)

        self.dist_table = dt.interpolate_dist_table(
            xs,
            dist_table,
            self.dist_table_density
        )

    def calculate_b_pot_matrix(self):
        """
        Compute the matrix of potentials generated by every
        source basis function at every electrode position.
        """
        self.calculate_b_pot_matrix_3D()

    def calculate_b_pot_matrix_3D(self):
        """
        Calculates b_pot_matrix - matrix containing the values of all
        the potential basis functions in all the electrode
        positions (essential for calculating the cross_matrix)
        """
        n_obs = self.elec_pos.shape[0]
        (nx, ny, nz) = self.X_src.shape
        n = nx * ny * nz

        self.b_pot_matrix = np.zeros((n, n_obs))

        for i in xrange(0, n):
            # finding the coordinates of the i-th source
            i_x, i_y, i_z = np.unravel_index(i, (nx, ny, nz))
            src = [self.X_src[i_x, i_y, i_z],
                   self.Y_src[i_x, i_y, i_z],
                   self.Z_src[i_x, i_y, i_z]]

            for j in xrange(0, n_obs):
                # for all the observation points
                # checking the distance between the observation point and
                # the source,
                # calculating the base value
                dist = norm(self.elec_pos[j] - src)

                self.b_pot_matrix[i, j] = dt.generated_potential(
                    dist,
                    self.dist_max,
                    self.dist_table
                )

    def calculate_b_src_matrix(self):
        """
        Compute the matrix of basis sources.
        """
        self.make_b_src_matrix_3D()

    def make_b_src_matrix_3D(self):
        """
        Calculate b_src_matrix - matrix containing containing the values of
        all the source basis functions in all the points at which we want to
        calculate the solution (essential for calculating the cross_matrix)
        """
        (nsx, nsy, nsz) = self.X_src.shape
        n = nsy * nsx * nsz  # total number of sources
        (ngx, ngy, ngz) = self.space_X.shape
        ng = ngx * ngy * ngz

        self.b_src_matrix = np.zeros((self.space_X.shape[0],
                                     self.space_X.shape[1],
                                     self.space_X.shape[2],
                                     n))

        for i in xrange(n):
            # getting the coordinates of the i-th source
            (i_x, i_y, i_z) = np.unravel_index(i, (nsx, nsy, nsz), order='F')
            z_src = self.Z_src[i_x, i_y, i_z]
            y_src = self.Y_src[i_x, i_y, i_z]
            x_src = self.X_src[i_x, i_y, i_z]

            self.b_src_matrix[:, :, :, i] = self.basis(
                self.space_X,
                self.space_Y,
                self.space_Z,
                [x_src, y_src, z_src],
                self.R
            )

        self.b_src_matrix = self.b_src_matrix.reshape(ng, n)

    def calculate_b_interp_pot_matrix(self):
        """
        Compute the matrix of potentials generated by every source
        basis function at every position in the interpolated space.
        """
        self.make_b_interp_pot_matrix_3D()

    def make_b_interp_pot_matrix_3D(self):
        (ngx, ngy, ngz) = self.space_X.shape
        ng = ngx * ngy * ngz
        (nsx, nsy, nsz) = self.X_src.shape
        n_src = nsy * nsx * nsz

        self.b_interp_pot_matrix = np.zeros((ngx, ngy, ngz, n_src))

        for i in xrange(0, n_src):
            # getting the coordinates of the i-th source
            i_x, i_y, i_z = np.unravel_index(i, (nsx, nsy, nsz), order='F')
            z_src = self.Z_src[i_x, i_y, i_z]
            y_src = self.Y_src[i_x, i_y, i_z]
            x_src = self.X_src[i_x, i_y, i_z]
            norms = np.sqrt((self.space_X - x_src)**2
                            + (self.space_Y - y_src)**2
                            + (self.space_Z - z_src)**2)

            self.b_interp_pot_matrix[:, :, :, i] = dt.generated_potential(
                norms,
                self.dist_max,
                self.dist_table
            )

        self.b_interp_pot_matrix = self.b_interp_pot_matrix.reshape(ng, n_src)

    def choose_lambda(self, lambdas, n_folds=1, n_iter=1):
        """
        Finds the optimal regularization parameter lambda for
        Tikhonov regularization using cross validation.
        """
        n = len(lambdas)
        errors = np.zeros(n)
        errors_iter = np.zeros(n_iter)
        for i, lambd in enumerate(lambdas):
            for j in xrange(n_iter):
                errors_iter[j] = cv.cross_validation(
                    lambd,
                    self.sampled_pots,
                    self.k_pot,
                    self.elec_pos.shape[0],
                    n_folds
                )
            errors[i] = np.mean(errors_iter)
        return lambdas[errors == min(errors)][0]


if __name__ == '__main__':
    elec_pos = np.array([(0, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 0),
                         (0, 1, 1), (1, 1, 0), (1, 0, 1), (1, 1, 1),
                         (0.5, 0.5, 0.5)])
    pots = np.array([-0.5, 0, -0.5, 0, 0, 0.2, 0, 0, 1])
    params = {
        'gdX': 0.05,
        'gdY': 0.05,
        'gdZ': 0.05,
        'n_sources': 64,
    }
    k = KCSD3D(elec_pos, pots, params)
    k.calculate_matrices()

    k.estimate_pots()
    k.estimate_csd()

    k.plot_all()