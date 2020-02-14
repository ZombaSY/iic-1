# Copyright 2018 Christoph Heindl.
#
# Licensed under MIT License
# ============================================================

import torch
import torch.nn.functional as F
from math import sin, cos

def tps(theta, ctrl, grid):
    '''Evaluate the thin-plate-spline (TPS) surface at xy locations arranged in a grid.
    The TPS surface is a minimum bend interpolation surface defined by a set of control points.
    The function value for a x,y location is given by

        TPS(x,y) := theta[-3] + theta[-2]*x + theta[-1]*y + \sum_t=0,T theta[t] U(x,y,ctrl[t])

    This method computes the TPS value for multiple batches over multiple grid locations for 2
    surfaces in one go.

    Params
    ------
    theta: Nx(T+3)x2 tensor, or Nx(T+2)x2 tensor
        Batch size N, T+3 or T+2 (reduced form) model parameters for T control points in dx and dy.
    ctrl: NxTx2 tensor or Tx2 tensor
        T control points in normalized image coordinates [0..1]
    grid: NxHxWx3 tensor
        Grid locations to evaluate with homogeneous 1 in first coordinate.

    Returns
    -------
    z: NxHxWx2 tensor
        Function values at each grid location in dx and dy.
    '''

    N, H, W, _ = grid.size()

    if ctrl.dim() == 2:
        ctrl = ctrl.expand(N, *ctrl.size())

    T = ctrl.shape[1]

    diff = grid[..., 1:].unsqueeze(-2) - ctrl.unsqueeze(1).unsqueeze(1)
    D = torch.sqrt((diff ** 2).sum(-1))
    U = (D ** 2) * torch.log(D + 1e-6)

    w, a = theta[:, :-3, :], theta[:, -3:, :]

    reduced = T + 2 == theta.shape[1]
    if reduced:
        w = torch.cat((-w.sum(dim=1, keepdim=True), w), dim=1)

        # U is NxHxWxT
    b = torch.bmm(U.view(N, -1, T), w).view(N, H, W, 2)
    # b is NxHxWx2
    z = torch.bmm(grid.view(N, -1, 3), a).view(N, H, W, 2) + b

    return z


def tps_grid(theta, ctrl, size):
    '''Compute a thin-plate-spline grid from parameters for sampling.

    Params
    ------
    theta: Nx(T+3)x2 tensor
        Batch size N, T+3 model parameters for T control points in dx and dy.
    ctrl: NxTx2 tensor, or Tx2 tensor
        T control points in normalized image coordinates [0..1]
    size: tuple
        Output grid size as NxCxHxW. C unused. This defines the output image
        size when sampling.

    Returns
    -------
    grid : NxHxWx2 tensor
        Grid suitable for sampling in pytorch containing source image
        locations for each output pixel.
    '''
    N, _, H, W = size

    grid = theta.new(N, H, W, 3)
    grid[:, :, :, 0] = 1.
    grid[:, :, :, 1] = torch.linspace(0, 1, W)
    grid[:, :, :, 2] = torch.linspace(0, 1, H).unsqueeze(-1)

    z = tps(theta, ctrl, grid)
    return (grid[..., 1:] + z) * 2 - 1  # [-1,1] range required by F.sample_grid


def tps_sparse(theta, ctrl, xy):
    if xy.dim() == 2:
        xy = xy.expand(theta.shape[0], *xy.size())

    N, M = xy.shape[:2]
    grid = xy.new(N, M, 3)
    grid[..., 0] = 1.
    grid[..., 1:] = xy

    z = tps(theta, ctrl, grid.view(N, M, 1, 3))
    return xy + z.view(N, M, 2)


def uniform_grid(shape):
    '''Uniformly places control points aranged in grid accross normalized image coordinates.

    Params
    ------
    shape : tuple
        HxW defining the number of control points in height and width dimension
    Returns
    -------
    points: HxWx2 tensor
        Control points over [0,1] normalized image range.
    '''
    H, W = shape[:2]
    c = torch.zeros(H, W, 2)
    c[..., 0] = torch.linspace(0, 1, W)
    c[..., 1] = torch.linspace(0, 1, H).unsqueeze(-1)
    return c


def tps_sample_params(batch_size, num_control_points, var=0.05):
    theta = torch.randn(batch_size, num_control_points + 3, 2) * var
    cnt_points = torch.rand(batch_size, num_control_points, 2)
    return theta, cnt_points


def tps_transform(x, theta, cnt_points, padding_mode='zeros'):
    device = x.device
    grid = tps_grid(theta, cnt_points, x.shape).type_as(x).to(device)
    return F.grid_sample(x, grid, padding_mode=padding_mode)


class RandomTPSTransform(object):
    def __init__(self, num_control=4, variance=0.05, padding_mode='zeros'):
        self.num_control = num_control
        self.var = variance
        self.padding_mode = padding_mode

    def __call__(self, x):
        theta, cnt_points = tps_sample_params(x.size(0), self.num_control, self.var)
        return tps_transform(x, theta, cnt_points)


def rotate_affine_grid(x, theta, padding_mode='zeros'):
    theta = torch.tensor([
        [cos(theta), sin(theta), 0.0],
        [-sin(theta), cos(theta), 0.0]
    ]).expand(x.size(0), -1, -1).to(x.device)

    grid = F.affine_grid(theta, x.shape)
    return F.grid_sample(x, grid, padding_mode=padding_mode)


def rotate_affine_grid_multi(x, theta, padding_mode='zeros'):
    theta = theta.to(x.device)
    cos_theta = torch.cos(theta)
    sin_theta = torch.sin(theta)

    transform = torch.zeros(x.size(0), 2, 3, dtype=x.dtype)
    transform[:, 0, 0] = cos_theta
    transform[:, 0, 1] = sin_theta
    transform[:, 1, 0] = - sin_theta
    transform[:, 1, 1] = cos_theta

    grid = F.affine_grid(transform, x.shape).to(x.device)
    return F.grid_sample(x, grid, padding_mode=padding_mode)


class Rotate(object):
    def __init__(self, theta=0.2):
        self.theta = theta

    def __call__(self, x):

        return rotate_affine_grid(x, self.theta)


class RotateMulti(object):
    def __init__(self, theta=0.2):
        self.theta = theta

    def __call__(self, x):
        theta = torch.full((x.size(0), ), self.theta, device=x.device)
        return rotate_affine_grid_multi(x, theta)


class RandRotate(object):
    def __init__(self, max=0.2):
        self.max = max

    def __call__(self, x):
        theta = torch.rand(x.size(0)) * 2 - 1
        theta = theta * self.max
        return rotate_affine_grid_multi(x, theta)


if __name__ == '__main__':
    c = torch.tensor([
        [0., 0],
        [1., 0],
        [1., 1],
        [0, 1],
    ]).unsqueeze(0)
    theta = torch.zeros(1, 4 + 3, 2)
    size = (1, 1, 6, 3)
    grid = tps_grid(theta, c, size)
    print(theta)
    print(theta.shape)
    print(c)
    print(c.shape)
    print(grid)
    print(grid.shape)
