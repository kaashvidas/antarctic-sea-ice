"""
Module 1, step 2 — ConvLSTM sea-ice concentration forecaster.

This is the one component in the whole platform with a real train/val/test
cycle (per the README's model-count table) — protect calendar time for it.

Architecture starting point: a standard ConvLSTM (Shi et al. 2015-style)
taking a short history of gridded concentration (+ optionally ERA5 wind/
temp channels) and predicting concentration N days ahead. See the
"Antarctic sea ice prediction with a ConvLSTM network" paper linked in
the README for a directly comparable published approach — use it to
sanity-check architecture choices and reported skill, not to copy
verbatim.

Stretch goal (only after this works end-to-end and baselines are beaten):
swap in a CNN-Transformer hybrid, per the Build Phases doc.
"""

import torch
import torch.nn as nn


class ConvLSTMCell(nn.Module):
    """Single ConvLSTM cell: like a standard LSTM cell, but the input-to-
    state and state-to-state transitions are convolutions instead of
    fully-connected layers, so spatial structure in the ice field is
    preserved instead of flattened away."""

    def __init__(self, input_dim: int, hidden_dim: int, kernel_size: int = 3):
        super().__init__()
        padding = kernel_size // 2
        self.hidden_dim = hidden_dim
        self.conv = nn.Conv2d(
            in_channels=input_dim + hidden_dim,
            out_channels=4 * hidden_dim,  # input, forget, output, cell gates
            kernel_size=kernel_size,
            padding=padding,
        )

    def forward(self, x, h_prev, c_prev):
        combined = torch.cat([x, h_prev], dim=1)
        gates = self.conv(combined)
        i, f, o, g = torch.chunk(gates, 4, dim=1)
        i, f, o = torch.sigmoid(i), torch.sigmoid(f), torch.sigmoid(o)
        g = torch.tanh(g)
        c = f * c_prev + i * g
        h = o * torch.tanh(c)
        return h, c

    def init_hidden(self, batch_size, spatial_shape, device):
        h, w = spatial_shape
        return (
            torch.zeros(batch_size, self.hidden_dim, h, w, device=device),
            torch.zeros(batch_size, self.hidden_dim, h, w, device=device),
        )


class SeaIceConvLSTM(nn.Module):
    """
    Sequence-to-one ConvLSTM: consumes `input_seq_len` days of gridded
    input channels, outputs a single day's forecast concentration map.
    Call it autoregressively (feeding each prediction back in as the
    newest history frame) to reach the full forecast_horizon_days from
    src/utils/grid.py.

    TODO once data is flowing (Phase 2):
      - Confirm input_dim: at minimum 1 (ice concentration), likely 3
        (+ ERA5 u-wind, v-wind) per the README's input table.
      - Confirm spatial_shape matches src.utils.grid.n_grid_cells().
      - Write train.py's training loop against this before tuning
        hidden_dim/kernel_size/num_layers.
    """

    def __init__(self, input_dim: int = 1, hidden_dim: int = 32, kernel_size: int = 3, num_layers: int = 2):
        super().__init__()
        self.num_layers = num_layers
        self.cells = nn.ModuleList([
            ConvLSTMCell(
                input_dim=input_dim if i == 0 else hidden_dim,
                hidden_dim=hidden_dim,
                kernel_size=kernel_size,
            )
            for i in range(num_layers)
        ])
        self.output_conv = nn.Conv2d(hidden_dim, 1, kernel_size=1)  # -> single concentration channel

    def forward(self, x_seq):
        """x_seq: (batch, time, channels, height, width)"""
        batch_size, seq_len, _, h, w = x_seq.shape
        device = x_seq.device

        hidden_states = [cell.init_hidden(batch_size, (h, w), device) for cell in self.cells]

        for t in range(seq_len):
            layer_input = x_seq[:, t]
            for layer_idx, cell in enumerate(self.cells):
                h_prev, c_prev = hidden_states[layer_idx]
                h_new, c_new = cell(layer_input, h_prev, c_prev)
                hidden_states[layer_idx] = (h_new, c_new)
                layer_input = h_new

        final_hidden = hidden_states[-1][0]
        return torch.sigmoid(self.output_conv(final_hidden))  # concentration in [0, 1]
