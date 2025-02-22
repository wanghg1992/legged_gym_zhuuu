# SPDX-FileCopyrightText: Copyright (c) 2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Copyright (c) 2021 ETH Zurich, Nikita Rudin

import numpy as np
import os
from datetime import datetime

import isaacgym
from legged_gym.envs import *
from legged_gym.utils import get_args, task_registry
import torch
import wandb


def train(args):
    env, env_cfg = task_registry.make_env(name=args.task, args=args)
    ppo_runner, train_cfg = task_registry.make_alg_runner(env=env, name=args.task, args=args)

    wandb.config = {
        "learning_rate": train_cfg.algorithm.learning_rate,
        "max_iterations": train_cfg.runner.max_iterations,
        "num_envs": env_cfg.env.num_envs,
    }
    csv_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    with open(os.path.join(csv_dir, 'result.csv'), 'a+') as f:
        f.write("################################################################################\n"
                "run time: \n"
                f"{datetime.now().strftime('%b%d_%H-%M-%S')}\n"
                "configs: \n"
                f"max_iterations={args.max_iterations}, run_name={args.run_name}, num_envs={args.num_envs}, "
                f"terrain={env_cfg.terrain.terrain_kwargs['type']}, measure_heights={env_cfg.terrain.measure_heights}, use_depth_images={env_cfg.control.get_depth_img}\n")

    ppo_runner.learn(num_learning_iterations=train_cfg.runner.max_iterations, init_at_random_ep_len=True)


if __name__ == '__main__':
    args = get_args([
        {"name": "--project", "type": str, "default": 'aliengo_vel', "help": "wandb project name."},
        {"name": "--debug", "type": str, "default": False, "help": "true for play."},
    ])
    log_mode = "online" if args.run_name != 'debug' else "disabled"
    wandb.init(project=args.project, entity="april-quadruped", name=args.run_name, sync_tensorboard=True, mode=log_mode)
    train(args)
