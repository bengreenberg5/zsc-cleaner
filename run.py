import ray
from ray.tune import register_env
from typarse import BaseParser

from cleaner.cleaner_env import *


class ArgParser(BaseParser):
    config: str = "simple_3x3"
    training_iters: int = 5
    checkpoint_freq: int = 0

    _help = {
        "config": "Path to the config of the experiment",
        "training_iters": "Number of training iterations",
        "checkpoint_freq": "How many training iterations between checkpoints. "
        "A value of 0 (default) disables checkpointing.",
        # "name": "Name of the run for checkpoints",
        # "checkpoint_path": "Which checkpoint to load, if any",
        # "wandb_project": "What project name in wandb?",
    }


def main():
    args = ArgParser()
    config = load_config(args.config)
    env_config = config["env_config"]
    ray_config = config["ray_config"]
    run_config = config["run_config"]

    ray.shutdown()
    ray.init()
    register_env("ZSC-Cleaner", lambda _: CleanerEnv(env_config))

    trainer = trainer_from_config(config)

    # Object to store training results in
    result = {}

    # Training loop
    for i in range(args.training_iters):
        if run_config["verbose"]:
            print(f"starting training iteration {i}")
        result = trainer.train()

        if args.checkpoint_freq != 0 and i % args.checkpoint_freq == 0:
            save_path = save_trainer(trainer, config)
            if run_config["verbose"]:
                print(f"saved trainer at {save_path}")

    # Save the state of the experiment at end
    save_path = save_trainer(trainer, config)
    if run_config["verbose"]:
        print(f"saved trainer at {save_path}")

    ray.shutdown()


if __name__ == "__main__":
    main()
