import numpy as np
from multiagent.core import World, Agent, Landmark, AgentState, Action
from multiagent.scenario import BaseScenario
from multiagent.scenarios.car_dynamics import Car
from multiagent.scenarios.cars_racing import CarRacing, FrictionDetector
from Box2D.b2 import (edgeShape, circleShape, fixtureDef, polygonShape, revoluteJointDef, contactListener)
import Box2D


colors = np.array([[0.65, 0.15, 0.15], [0.15, 0.65, 0.15], [0.15, 0.15, 0.65],
                   [0.15, 0.65, 0.65], [0.65, 0.15, 0.65], [0.65, 0.65, 0.15]])

import matplotlib.pyplot as plt
class DynamicAgent(Agent):
    def __init__(self):
        super(DynamicAgent, self).__init__()
        self.body = None

class RoadWorld(World):
    def __init__(self):
        super(RoadWorld, self).__init__()
        self.track = None
        self.physics = None


class Scenario(BaseScenario):
    def make_world(self):
        world = RoadWorld()
        # set any world properties first
        world.dim_p = 2 # x, y, orientation, speed
        world.collaborative = True
        road = CarRacing()
        world.track = road.track
        world.physics = road.physics
        world.viewer = road.viewer
        world.viewer.close()
        world.physical_step = road.step
        world.show_track = road.render
        world.close_race = road.close

        # add agents
        self.num_agents = 3
        world.agents = [DynamicAgent() for i in range(self.num_agents)]
        for i, agent in enumerate(world.agents):
            agent.name = 'agent %d' % i
            agent.collide = True
            agent.silent = True
            agent.body = Car()
            agent.size = 0.01

        # add landmarks
        num_land = 20
        world.landmarks = [Landmark() for i in range(num_land)]
        for i, landmark in enumerate(world.landmarks):
            landmark.name = 'landmark %d' % i
            landmark.collide = False
            landmark.movable = False
            landmark.size = 0.01
        # make initial conditions
        self.reset_world(world)
        return world

    def manual_control(self, world):

        from pyglet.window import key
        a = np.array([[0.0, 0.0, 0.0] for _ in range(len(world.agents))])

        def key_press(k, mod):
            global restart
            if k == 0xff0d: restart = True
            if k == key.LEFT:  a[0, 0] = -1.0
            if k == key.RIGHT: a[0, 0] = +1.0
            if k == key.UP:    a[0, 1] = +1.0
            if k == key.DOWN:  a[0, 2] = +0.8  # set 1.0 for wheels to block to zero rotation

            if k == key.A:  a[2, 0] = -1.0
            if k == key.D:  a[2, 0] = +1.0
            if k == key.W:  a[2, 1] = +1.0
            if k == key.S:  a[2, 2] = +0.8  # set 1.0 for wheels to block to zero rotation

        def key_release(k, mod):
            if k == key.LEFT and np.any(a[0, 0] == -1.0): a[0, 0] = 0
            if k == key.RIGHT and np.any(a[:, 0] == +1.0): a[0, 0] = 0
            if k == key.UP:    a[0, 1] = 0
            if k == key.DOWN:  a[0, 2] = 0

            if k == key.A and np.any(a[2, 0] == -1.0): a[2, 0] = 0
            if k == key.D and np.any(a[2, 0] == +1.0): a[2, 0] = 0
            if k == key.W:    a[2, 1] = 0
            if k == key.S:  a[2, 2] = 0

        world.viewer.window.on_key_press = key_press
        world.viewer.window.on_key_release = key_release

        steps = 0
        restart = False
        while True:
            done = world.physical_step(a, [agent.body for agent in world.agents])
            if done: break
            world.show_track([agent.body for agent in world.agents])

            #total_reward += r
            # if steps % 200 == 0 or done:
            #     #print("\naction " + str(["{:+0.2f}".format(x) for x in a]))
            #     print("step {} total_reward {:+0.2f}".format(steps, total_reward))
            #
            #     road = np.array([list(t) for t in world.track])
            #     #plt.scatter(road[:, 2], road[:, 3])
            #     plt.imshow(s)
            #     #plt.show()
            #     plt.savefig(f"test{steps}.jpeg")
            steps += 1
        world.close_race()

    def normalize_position(self, track, pos):
        x, y = pos
        track_width = abs(max(track[:, 2]) - min(track[:, 2]))
        track_height = abs(max(track[:, 3]) - min(track[:, 3]))
        x_new = (x - min(track[:, 2])) / track_width - .5
        y_new = (y - min(track[:, 3])) / track_height - .5
        return np.array([x_new, y_new])

    def reset_world(self, world):
        angle, x, y = world.track[0][1:4]
        start_pos = world.track[0][2:4]
        # random properties for agents
        for i, agent in enumerate(world.agents):
            agent.color = colors[i]
            agent.action_callback = None
            agent.body.make(angle, x, y, world.physics, agent.color)
            agent.state.p_pos = self.normalize_position(world.track, start_pos) + np.random.uniform(-.1,+.1, world.dim_p)
            agent.state.p_vel = np.zeros(world.dim_p)
            #plt.scatter(agent.state.p_pos[0], agent.state.p_pos[1], color='r', s=100)

        for i, landmark in enumerate(world.landmarks):
            landmark.color = np.array([0.75, 0.75, 0.75])
            idx = len(world.track) // len(world.landmarks) * i
            pos = world.track[idx, 2:4]
            landmark.state.p_pos = self.normalize_position(world.track, pos)
            landmark.state.p_vel = np.zeros(world.dim_p)
            #plt.scatter(landmark.state.p_pos[0], landmark.state.p_pos[1], color='b')
        #plt.savefig('track.png')
        #self.manual_control(world)

    def is_collision(self, agent1, agent2):
        delta_pos = agent1.state.p_pos - agent2.state.p_pos
        dist = np.sqrt(np.sum(np.square(delta_pos)))
        dist_min = agent1.size + agent2.size
        return True if dist < dist_min else False

    def reward(self, agent, world):
        # Agents are rewarded based on minimum agent distance to each landmark, penalized for collisions
        rew = 0
        dists = [np.sqrt(np.sum(np.square(agent.state.p_pos - l.state.p_pos))) for l in world.landmarks]
        i = np.argmin(dists, axis=0)
        rew -= dists[(i + 1) % len(world.landmarks)]
        # if agent.collide:
        #     for a in world.agents:
        #         if self.is_collision(a, agent):
        #             rew -= 1
        return rew

    def observation(self, agent, world):
        # agent.state.p_pos = np.array([agent.body.hull.position.x, agent.body.hull.position.y])
        # agent.state.p_vel = agent.body.wheels[-1].gas * np.array([np.cos(agent.body.wheels[0].steer), np.sin(agent.body.wheels[0].steer)])

        # get positions of all entities in this agent's reference frame
        entity_pos = []
        for entity in world.landmarks:  # world.entities:
            entity_pos.append(entity.state.p_pos - agent.state.p_pos)
        # entity colors
        entity_color = []
        for entity in world.landmarks:  # world.entities:
            entity_color.append(entity.color)
        # communication of all other agents
        other_pos = []
        for other in world.agents:
            if other is agent: continue
            other_pos.append(other.state.p_pos - agent.state.p_pos)
        return np.concatenate([agent.state.p_vel] + [agent.state.p_pos] + entity_pos + other_pos)

    def benchmark_data(self, agent, world):
        return (self.reward(agent, world), )