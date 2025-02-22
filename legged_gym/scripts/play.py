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
import time

from legged_gym import LEGGED_GYM_ROOT_DIR
import os
from datetime import datetime

import isaacgym
from legged_gym.envs import *
from legged_gym.utils import get_args, export_policy_as_jit, task_registry, Logger

import numpy as np
import torch
from Commander import GamepadCommander


def get_command_from_gamepad(obs, cmd_range):
    global GpC
    cmd = np.array(GpC.read_command())
    vel_x = cmd_range["vel_x"]
    vel_y = cmd_range["vel_y"]
    w = cmd_range["w"]
    cmd[0] = vel_x[1] * cmd[0] if cmd[0] > 0 else vel_x[0] * abs(cmd[0])
    cmd[1] = vel_y[1] * cmd[1] if cmd[1] > 0 else vel_y[0] * abs(cmd[1])
    cmd[2] = w[1] * cmd[2] if cmd[0] > 0 else w[0] * abs(cmd[2])
    print("velx, vely, w:", cmd)
    cmd_norm = np.linalg.norm(cmd) < 0.01
    # print("cmd:", cmd)
    obs[:, 0:3] = torch.tensor(cmd)
    obs[:, -1] = torch.tensor(cmd_norm)
    return obs


def play(args):
    env_cfg, train_cfg = task_registry.get_cfgs(name=args.task)
    # override some parameters for testing
    env_cfg.env.num_envs = min(env_cfg.env.num_envs, 4)
    env_cfg.terrain.num_rows = 1
    env_cfg.terrain.num_cols = 1
    env_cfg.terrain.terrain_length = 30
    env_cfg.terrain.terrain_width = 30
    env_cfg.terrain.curriculum = False
    env_cfg.commands.step_cmd = True
    env_cfg.noise.add_noise = False
    env_cfg.domain_rand.randomize_friction = False
    env_cfg.domain_rand.push_robots = False
    env_cfg.control.wandb_log = False

    # init GamepadCommander--xbox
    global GpC
    if args.gamepad:
        GpC = GamepadCommander()

    # prepare environment
    cmd_range = {
        "vel_x": [-3, 3],
        "vel_y": [-2, 2],
        "w": [-3., 3.],
    }
    env, _ = task_registry.make_env(name=args.task, args=args, env_cfg=env_cfg)
    obs = env.get_observations()
    if args.gamepad:
        obs = get_command_from_gamepad(obs, cmd_range)

    # load policy
    train_cfg.runner.resume = True
    ppo_runner, train_cfg = task_registry.make_alg_runner(env=env, name=args.task, args=args, train_cfg=train_cfg)
    policy = ppo_runner.get_inference_policy(device=env.device)
    # policy = torch.jit.load('/home/zdy/raisim_gym/aliengo-AirTime(-0.4)@40000-1130.pt')
    # policy = policy.to(self.device)
    # export policy as a jit module (used to run it from C++)
    if EXPORT_POLICY:
        path = os.path.join(LEGGED_GYM_ROOT_DIR, 'logs', train_cfg.runner.experiment_name, 'exported', 'policies')
        # export_policy_as_jit(ppo_runner.alg.actor_critic, path)
        print('Exported policy as jit script to: ', path)

    logger = Logger(env.dt)
    robot_index = 0  # which robot is used for logging
    joint_index = 1  # which joint is used for logging
    stop_state_log = 200  # number of steps before plotting states
    stop_rew_log = env.max_episode_length  # number of steps before print average episode rewards 1000
    camera_position = np.array(env_cfg.viewer.pos, dtype=np.float64)
    camera_vel = np.array([1., 1., 0.])
    camera_direction = np.array(env_cfg.viewer.lookat) - np.array(env_cfg.viewer.pos)
    img_idx = 0
    re = torch.zeros(env.num_envs, device=env.device)
    torch.inference_mode().__enter__()
    for i in range(int(2.0 * env.max_episode_length) + 1):
        actions = policy(obs.contiguous())
        time0 = time.time()
        obs, _, rews, dones, infos = env.step(actions)
        if args.gamepad:
            obs = get_command_from_gamepad(obs, cmd_range)
        # print(f'step time: {(time.time() - time0) * 1000} ms')
        re += rews
        # print("play:", env.commands)
        if RECORD_FRAMES:
            if i % 2:
                filename = os.path.join(LEGGED_GYM_ROOT_DIR, 'logs', train_cfg.runner.experiment_name, 'exported', 'frames', f"{img_idx}.png")
                env.gym.write_viewer_image_to_file(env.viewer, filename)
                img_idx += 1
        if MOVE_CAMERA:
            camera_position += camera_vel * env.dt
            env.set_camera(camera_position, camera_position + camera_direction)

        if i < stop_state_log:
            logger.log_states(
                {
                    'dof_pos_target': actions[robot_index, joint_index].item() * env.cfg.control.action_scale,
                    'dof_pos': env.dof_pos[robot_index, joint_index].item(),
                    'dof_vel': env.dof_vel[robot_index, joint_index].item(),
                    'dof_torque': env.torques[robot_index, joint_index].item(),
                    'command_x': env.commands[robot_index, 0].item(),
                    'command_y': env.commands[robot_index, 1].item(),
                    'command_yaw': env.commands[robot_index, 2].item(),
                    'base_vel_x': env.base_lin_vel[robot_index, 0].item(),
                    'base_vel_y': env.base_lin_vel[robot_index, 1].item(),
                    'base_vel_z': env.base_lin_vel[robot_index, 2].item(),
                    'base_vel_yaw': env.base_ang_vel[robot_index, 2].item(),
                    'contact_forces_z': env.contact_forces[robot_index, env.feet_indices, 2].cpu().numpy()
                }
            )
        elif i == stop_state_log:
            # logger.plot_states()
            continue
        if "episode" in infos.keys():
            num_episodes = torch.sum(env.reset_buf).item()
            if num_episodes > 0:
                logger.log_rewards(infos["episode"], num_episodes)
        if i == stop_rew_log:
            logger.print_rewards()
    print("reward in {num} step: {reward}".format(num=int(1.0 * env.max_episode_length) + 1, reward=torch.mean(re)))
    time.sleep(1)


if __name__ == '__main__':
    EXPORT_POLICY = False
    RECORD_FRAMES = False
    MOVE_CAMERA = False
    args = get_args([
        {"name": "--debug", "action": "store_true", "default": False, "help": "true for play."},
        {"name": "--gamepad", "action": "store_true", "default": False, "help": "use gamepad."},
    ])
    play(args)
