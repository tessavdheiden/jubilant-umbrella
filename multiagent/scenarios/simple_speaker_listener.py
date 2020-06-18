import numpy as np
from multiagent.core import World, Agent, Landmark
from multiagent.scenario import BaseScenario

class Scenario(BaseScenario):
    def make_world(self):
        world = World()
        # set any world properties first
        world.dim_c = 3
        num_landmarks = 3
        world.collaborative = True
        # add agents
        world.agents = [Agent() for i in range(2)]
        for i, agent in enumerate(world.agents):
            agent.name = 'agent %d' % i
            agent.collide = False
            agent.size = 0.075
        # speaker
        world.agents[0].movable = False
        # listener
        world.agents[1].silent = True
        # add landmarks
        world.landmarks = [Landmark() for i in range(num_landmarks)]
        for i, landmark in enumerate(world.landmarks):
            landmark.name = 'landmark %d' % i
            landmark.collide = False
            landmark.movable = False
            landmark.size = 0.04
        # make initial conditions
        self.reset_world(world)
        return world

    def reset_world(self, world):
        # assign goals to agents
        for agent in world.agents:
            agent.goal_a = None
            agent.goal_b = None
        # want listener to go to the goal landmark
        world.agents[0].goal_a = world.agents[1]
        world.agents[0].goal_b = np.random.choice(world.landmarks)
        # random properties for agents
        for i, agent in enumerate(world.agents):
            agent.color = np.array([0.25,0.25,0.25])               
        # random properties for landmarks
        world.landmarks[0].color = np.array([0.65,0.15,0.15])
        world.landmarks[1].color = np.array([0.15,0.65,0.15])
        world.landmarks[2].color = np.array([0.15,0.15,0.65])
        # special colors for goals
        world.agents[0].goal_a.color = world.agents[0].goal_b.color + np.array([0.45, 0.45, 0.45])
        # set random initial states
        for agent in world.agents:
            agent.state.p_pos = np.random.uniform(-1,+1, world.dim_p)
            agent.state.p_vel = np.zeros(world.dim_p)
            agent.state.c = np.zeros(world.dim_c)
        for i, landmark in enumerate(world.landmarks):
            landmark.state.p_pos = np.random.uniform(-1,+1, world.dim_p)
            landmark.state.p_vel = np.zeros(world.dim_p)

    def benchmark_data(self, agent, world):
        # returns data for benchmarking purposes
        return (self.reward(agent, world), )

    def reward(self, agent, world):
        # squared distance from listener to landmark
        a = world.agents[0]
        dist2 = np.sum(np.square(a.goal_a.state.p_pos - a.goal_b.state.p_pos))
        return -dist2

    def observation(self, agent, world):
        # goal color
        goal_color = np.zeros(world.dim_color)
        if agent.goal_b is not None:
            goal_color = agent.goal_b.color

        # get positions of all entities in this agent's reference frame
        entity_pos = []
        for entity in world.landmarks:
            entity_pos.append(entity.state.p_pos - agent.state.p_pos)

        # communication of all other agents
        comm = []
        for other in world.agents:
            if other is agent or (other.state.c is None): continue
            comm.append(other.state.c)
        
        # speaker
        if not agent.movable:
            return np.concatenate([goal_color])
        # listener
        if agent.silent:
            return np.concatenate([agent.state.p_vel] + entity_pos + comm)


from multiagent.scenarios.mdp import BaseMDP
from multiagent.scenarios.transition_utils import _dist_locs, _index_to_cell, _cell_to_index, vecmod
from estimate_empowerment import empowerment
import itertools
from functools import reduce


class MDP(BaseMDP):
    def __init__(self, dims, n_step, act=None):

        land_s = list(itertools.permutations(np.arange(dims[0] * dims[1]), 3))
        a_s = np.arange(dims[0] * dims[1])

        values = [([s1, s2, s3], [_dist_locs(s, s1, dims), _dist_locs(s, s2, dims), _dist_locs(s, s3, dims)], s) for (s1, s2, s3) in land_s for s in a_s]

        self.configurations = dict(list(enumerate(values))) # TODO: some land_dist are similar

        self.actions = {
            "N": np.array([1, 0]),      # UP
            "S": np.array([-1, 0]),     # DOWN
            "E": np.array([0, 1]),      # RIGHT
            "W": np.array([0, -1]),     # LEFT
            "_": np.array([0, 0])       # STAY
        }
        if act is None:
            self.T = self.compute_transition(dims, self.configurations, self.act)
        else:
            self.T = self.compute_transition(dims, self.configurations, act)
        self.Tn = self.compute_transition_nstep(T=self.T, n_step=n_step)

    def act(self, s, a, dims, prob=1., toroidal=False):
        """ get updated state after action
        s  : state, index of grid position
        a : action
        prob : probability of performing action
        """
        rnd = np.random.rand()
        if rnd > prob:
            a = np.random.choice(list(filter(lambda x: x != a, self.actions.keys())))
        state = _index_to_cell(s, dims)

        new_state = state + self.actions[a]
        # can't move off grid
        if toroidal:
            new_state = vecmod(new_state, dims)
        elif np.any(new_state < np.zeros(2)) or np.any(new_state >= dims):
            return _cell_to_index(state, dims)
        return _cell_to_index(new_state, dims)

    def _find_s_in_dict(self, s, s1, s2, s3):
        for k, v in self.configurations.items():
            (land_s, land_p, ss) = v
            (ss1, ss2, ss3) = land_s
            if s == ss and s1 == ss1 and s2 == ss2 and s3 == ss3:
                return k
        return -1

    def _find_p_in_dict(self, s, s1, s2, s3, dims):
        d1 = _dist_locs(s, s1, dims)
        d2 = _dist_locs(s, s2, dims)
        d3 = _dist_locs(s, s3, dims)
        klist = []
        for k, v in self.configurations.items():
            (land_s, land_p, ss) = v
            (dd1, dd2, dd3) = land_p
            if d1 == dd1 and d2 == dd2 and d3 == dd3:
                klist.append(k)
        return klist

    def compute_transition(self, dims, locations, act, det=1.):
        T = np.zeros([len(locations), len(self.actions), len(locations)])

        for k, v in locations.items():
            (land_s, land_p, s) = v
            (s1, s2, s3) = land_s
            for i, a in enumerate(self.actions.keys()):
                s_new = act(s, a, dims)
                #k_new = self._find_s_in_dict(s_new, s1, s2, s3) # TODO: find by s or by p? s is faster and unique, p corresponds to env
                klist = self._find_p_in_dict(s_new, s1, s2, s3, dims)
                for k_new in klist:
                    T[k_new, i, k] += det / len(klist)

        return T

    def compute_transition_nstep(self, T, n_step):
        n_states, n_actions, _ = T.shape
        nstep_actions = np.array(list(itertools.product(range(n_actions), repeat=n_step)))
        Bn = np.zeros([n_states, len(nstep_actions), n_states])
        for i, an in enumerate(nstep_actions):
            Bn[:, i, :] = reduce((lambda x, y: np.dot(y, x)), map((lambda a: T[:, a, :]), an))
        return Bn



if __name__ == '__main__':
    mdp = MDP(dims=(3, 3), n_step=1)
    E = np.zeros(len(mdp.configurations))

    for k, v in mdp.configurations.items():
        E[k] = empowerment(T=mdp.Tn, det=.9, n_step=1, state=k)
    idx = np.argsort(E)
    print(f'min E = {E[idx[0]]} max E = {E[idx[-1]]}')
    print(f'min c = {mdp.configurations[idx[0]]} max c = {mdp.configurations[idx[-1]]}')
    print(f'equal idx min = {[mdp.configurations[key] for key in np.where(E==E[idx[-1]])[0].tolist()]}')