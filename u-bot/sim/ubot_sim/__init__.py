from gymnasium.envs.registration import register

register(id="UBotNavigation-v0", entry_point="ubot_sim.env:UBotNavigationEnv")
register(id="UBotWaypoints-v0", entry_point="ubot_sim.waypoints:UBotWaypointsEnv")
