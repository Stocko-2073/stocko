"""mjlab tasks for phone_girl, registered through the mjlab.tasks entry point."""

from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg
from mjlab.tasks.registry import register_mjlab_task

from phone_girl.deploy import PhoneGirlRunner
from phone_girl.tasks.env import stand_cfg, stand_ideal_cfg, walk_cfg


def ppo(experiment: str, iterations: int) -> RslRlOnPolicyRunnerCfg:
    """PPO with an asymmetric critic: the actor sees only what the phone can, the critic more."""
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(hidden_dims=(256, 256, 128), activation="elu", obs_normalization=True,
                            distribution_cfg={"class_name": "GaussianDistribution", "init_std": 0.5,
                                              "std_type": "scalar"}),
        critic=RslRlModelCfg(hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True),
        algorithm=RslRlPpoAlgorithmCfg(learning_rate=1e-3, num_learning_epochs=5, num_mini_batches=4,
                                       entropy_coef=0.005, desired_kl=0.01, gamma=0.99, lam=0.95),
        experiment_name=experiment, num_steps_per_env=24, max_iterations=iterations, save_interval=100,
        logger="tensorboard",
    )


register_mjlab_task(task_id="PhoneGirl-Stand", env_cfg=stand_cfg(), play_env_cfg=stand_cfg(play=True),
                    rl_cfg=ppo("phone_girl_stand", 3000), runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Stand-Ideal", env_cfg=stand_ideal_cfg(),
                    play_env_cfg=stand_ideal_cfg(play=True), rl_cfg=ppo("phone_girl_stand_ideal", 3000),
                    runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Walk", env_cfg=walk_cfg(), play_env_cfg=walk_cfg(play=True),
                    rl_cfg=ppo("phone_girl_walk", 6000), runner_cls=PhoneGirlRunner)
