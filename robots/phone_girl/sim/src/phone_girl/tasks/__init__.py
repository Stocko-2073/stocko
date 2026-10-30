"""mjlab tasks for phone_girl, registered through the mjlab.tasks entry point.

The tasks run over the default USB-C NCM link; the `-Ble` tasks run over BLE,
the other hardware option.
"""

from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg
from mjlab.tasks.registry import register_mjlab_task

from phone_girl.deploy import PhoneGirlRunner
from phone_girl.link import LinkCfg, ble_link
from phone_girl.tasks.env import stand_cfg, stand_ideal_cfg, walk_cfg

# Discounting and rollouts tuned at a 15 ms tick, rescaled to keep their meaning in seconds.
REFERENCE_PERIOD_S = 0.015
ROLLOUT_S = 0.36  # simulated time per robot per iteration: 24 ticks at 15 ms


def ppo(experiment: str, iterations: int, period_s: float = LinkCfg.interval_s) -> RslRlOnPolicyRunnerCfg:
    """PPO with an asymmetric critic: the actor sees only what the phone can, the critic more.

    Discount and GAE decay per second as 0.99 and 0.95 per 15 ms tick do, and an
    iteration simulates 0.36 s per robot, whatever the control period.
    """
    ticks = period_s / REFERENCE_PERIOD_S
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(hidden_dims=(256, 256, 128), activation="elu", obs_normalization=True,
                            distribution_cfg={"class_name": "GaussianDistribution", "init_std": 0.5,
                                              "std_type": "scalar"}),
        critic=RslRlModelCfg(hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True),
        algorithm=RslRlPpoAlgorithmCfg(learning_rate=1e-3, num_learning_epochs=5, num_mini_batches=4,
                                       entropy_coef=0.005, desired_kl=0.01, gamma=0.99 ** ticks,
                                       lam=0.95 ** ticks),
        experiment_name=experiment, num_steps_per_env=round(ROLLOUT_S / period_s), max_iterations=iterations,
        save_interval=100, logger="tensorboard",
    )


usb, ble = LinkCfg(), ble_link()
register_mjlab_task(task_id="PhoneGirl-Stand", env_cfg=stand_cfg(), play_env_cfg=stand_cfg(play=True),
                    rl_cfg=ppo("phone_girl_stand", 3000, usb.interval_s), runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Stand-Ideal", env_cfg=stand_ideal_cfg(),
                    play_env_cfg=stand_ideal_cfg(play=True), rl_cfg=ppo("phone_girl_stand_ideal", 3000, usb.interval_s),
                    runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Walk", env_cfg=walk_cfg(), play_env_cfg=walk_cfg(play=True),
                    rl_cfg=ppo("phone_girl_walk", 6000, usb.interval_s), runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Stand-Ble", env_cfg=stand_cfg(link=ble_link()),
                    play_env_cfg=stand_cfg(play=True, link=ble_link()),
                    rl_cfg=ppo("phone_girl_stand_ble", 3000, ble.interval_s), runner_cls=PhoneGirlRunner)
register_mjlab_task(task_id="PhoneGirl-Walk-Ble", env_cfg=walk_cfg(link=ble_link()),
                    play_env_cfg=walk_cfg(play=True, link=ble_link()),
                    rl_cfg=ppo("phone_girl_walk_ble", 6000, ble.interval_s), runner_cls=PhoneGirlRunner)
