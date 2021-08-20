from collections import defaultdict
from matplotlib import animation
import os
from pathlib import Path
import stat
from typarse import BaseParser
from typing import Dict, Optional
import wandb

import ray
from ray.rllib.evaluation import MultiAgentEpisode
from ray.rllib.utils.typing import PolicyID
from ray.rllib import RolloutWorker, BaseEnv, Policy
from ray.rllib.agents import DefaultCallbacks
from ray.tune import register_env

from cleaner.agent import Agent
from cleaner.cleaner_env import *


class ArgParser(BaseParser):
    config: str = "simple_3x3"
    name: str = "cleaner"
    policy: str = "ppo"
    training_iters: int = 5
    checkpoint_freq: int = 25
    eval_freq: int = 25

    _help = {
        "config": "Path to the config of the experiment",
        "name": "Name of subdirectory containing results for this experiment",
        "policy": "RL algorithm",
        "training_iters": "Number of training iterations",
        "checkpoint_freq": "How many training iterations between checkpoints; a value of 0 (default) disables checkpointing",
        "eval_freq": "How many training iterations between evaluations",
    }


def evaluate(agents, config, eval_run_name, checkpoint_num=None, record=True):
    # create env
    done = {"__all__": False}
    env = CleanerEnv(config["env_config"], run_name=eval_run_name)
    fig, ax = plt.subplots()
    images = []

    # run episode
    rewards = []
    actions = {}
    while not done["__all__"]:
        if record:
            im = env.game.render(fig, ax)
            images.append([im])
        for agent_name in agents.keys():
            policy_id = (
                agent_name if config["run_config"]["heterogeneous"] else "agent_policy"
            )
            actions[agent_name] = agents[agent_name].trainer.compute_action(
                observation=env.game.agent_obs()[agent_name],
                policy_id=policy_id,
            )
        _, reward, done, _ = env.step(actions)
        rewards.append(reward)

    # create video
    if record:
        if checkpoint_num:
            video_filename = f"{RAY_DIR}/{eval_run_name}/checkpoint_{str(checkpoint_num).zfill(6)}/video.mp4"
        else:
            video_filename = f"{RAY_DIR}/{eval_run_name}/video.mp4"
        ani = animation.ArtistAnimation(
            fig, images, interval=200, blit=True, repeat_delay=10000
        )
        ani.save(video_filename)
        print(f"saved video at {video_filename}")

    print(f"episode reward: {sum([sum(r.values()) for r in rewards])}")


def train(
    agents,
    trainer,
    training_iters,
    run_name,
    config,
    results_dir,
    checkpoint_freq=0,
    eval_freq=0,
    verbose=True,
):
    for i in range(training_iters):
        if verbose:
            print(f"starting training iteration {i}")
        trainer.train()
        if checkpoint_freq != 0 and i % checkpoint_freq == 0:
            save_trainer(trainer, path=results_dir, verbose=verbose)
        if eval_freq != 0 and i % eval_freq == 0:
            evaluate(
                agents=agents,
                config=config,
                eval_run_name=run_name,
                checkpoint_num=i + 1,
                record=True,
            )
    save_trainer(trainer, path=results_dir, verbose=verbose)
    evaluate(
        agents=agents,
        config=config,
        eval_run_name=run_name,
        checkpoint_num=training_iters,
        record=True,
    )


def main():
    args = ArgParser()
    config = load_config(args.config)
    env_config = config["env_config"]
    ray_config = config["ray_config"]
    run_config = config["run_config"]
    eval_config = {
        "agents": [
            (args.name, i, args.training_iters) for i in range(env_config["num_agents"])
        ],
        "env_config": env_config,
        "eval_name": args.name,
    }

    # initialize ray
    ray.shutdown()
    ray.init()
    register_env("ZSC-Cleaner", lambda _: CleanerEnv(env_config, run_name=args.name))

    # initialize Weights & Biases
    wandb.init(
        project=run_config["wandb_project"],
        entity=os.environ["USERNAME"],
        config=config,
        monitor_gym=True,
        sync_tensorboard=True,
        reinit=True,
    )

    # create agents
    agents = {}
    for i in range(config["env_config"]["num_agents"]):
        agent = Agent(args.policy)
        agent.prepare_to_run(run_name=args.name, agent_num=i)
        agents[agent.name] = agent

    # train model(s)
    results_dir = f"{os.path.expanduser('~')}/ray_results/{args.name}/"
    trainer = Agent.create_trainer(
        agents=agents, policy_name=args.policy, config=config, results_dir=results_dir
    )
    train(
        agents=agents,
        trainer=trainer,
        training_iters=args.training_iters,
        run_name=args.name,
        config=config,
        results_dir=results_dir,
        checkpoint_freq=args.checkpoint_freq,
        eval_freq=args.eval_freq,
        verbose=config["run_config"]["verbose"],
    )
    ray.shutdown()
    print(f"finished training {args.name}")


if __name__ == "__main__":
    main()
