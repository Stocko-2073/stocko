"""Exported policies: the ONNX file acts like the trained actor and carries the contract."""

from dataclasses import asdict

import numpy as np
import onnxruntime
import pytest
import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg

from phone_girl import deploy
from phone_girl.robot import JOINTS
from phone_girl.tasks.env import BALANCE_JOINTS


def test_onnx_matches_actor_and_carries_contract(tmp_path):
    cfg = load_env_cfg("PhoneGirl-Stand")
    cfg.scene.num_envs = 2
    env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg, device="cpu"))
    agent = load_rl_cfg("PhoneGirl-Stand")
    runner = deploy.PhoneGirlRunner(env, asdict(agent), str(tmp_path), "cpu")
    observations = env.get_observations()
    # Give the normalizer non-trivial statistics before exporting.
    runner.alg.actor.update_normalization(observations)
    runner.save(str(tmp_path / "model_0.pt"))
    exported = next(tmp_path.glob("*_0.onnx"))

    session = onnxruntime.InferenceSession(str(exported))
    actor_obs = observations["actor"][:1].numpy().astype(np.float32)
    onnx_action = session.run(None, {session.get_inputs()[0].name: actor_obs})[0]
    with torch.no_grad():
        torch_action = runner.alg.get_policy()(observations[:1], stochastic_output=False).numpy()
    np.testing.assert_allclose(onnx_action, torch_action, atol=1e-5)

    contract = deploy.read(str(exported))
    assert [j["name"] for j in contract["joints"]] == list(JOINTS)
    assert contract["version"] == 3 and contract["control_period_s"] == pytest.approx(0.010)
    assert contract["link"]["transport"] == "usb-ncm"
    sizes = {t["name"]: t["size"] for t in contract["observation"]["terms"]}
    assert sum(sizes.values()) * contract["observation"]["history"] == actor_obs.shape[1]
    assert sizes["joint_effort"] == len(JOINTS) and sizes["gravity"] == 3
    scales = dict(zip(JOINTS, contract["action"]["scale"]))
    assert {j for j, s in scales.items() if s} == set(BALANCE_JOINTS)  # Stand holds the rest at home
    env.close()


@pytest.mark.parametrize("task, period, transport", [("PhoneGirl-Stand-Ble", 0.015, "ble"),
                                                     ("PhoneGirl-Stand-Ideal", 0.010, "ideal")])
def test_contract_names_the_link(task, period, transport):
    cfg = load_env_cfg(task)
    cfg.scene.num_envs = 1
    env = ManagerBasedRlEnv(cfg, device="cpu")
    contract = deploy.contract(env)
    assert contract["control_period_s"] == pytest.approx(period) and contract["link"]["transport"] == transport
    env.close()
