from keras.layers import Input, Dense, Flatten, Concatenate, Conv2D, Dropout, LeakyReLU
from keras.losses import mean_squared_error
from keras.models import Model, clone_model, load_model
from keras.optimizers import SGD, Adam, RMSprop
import numpy as np


def softmax(x, temperature=1):
    return np.exp(x / temperature) / np.sum(np.exp(x / temperature))


class Agent(object):

    def __init__(self, color=1):
        self.color = color

    def evaluate(self, move, env, gamma=0.9):
        episode_end, reward = env.step(move)
        successor_value = self.predict(env.layer_board)
        returns = reward + gamma * successor_value
        env.board.pop()
        env.init_layer_board()
        return returns

    def predict(self, layer_board):
        return np.random.randint(-5, 5) / 5


class RandomAgent(object):

    def __init__(self, color=1):
        self.color = color

    def predict(self, board_layer):
        return np.random.randint(-5, 5) / 5

    def select_move(self, moves, successor_values):
        return moves[np.argmax(successor_values)]


class GreedyAgent(object):

    def __init__(self, color=-1):
        self.color = color

    def evaluate(self, layer_board, noise=True):
        layer_board1 = layer_board[0, :, :, :]
        pawns = 1 * np.sum(layer_board1[0, :, :])
        rooks = 5 * np.sum(layer_board1[1, :, :])
        minor = 3 * np.sum(layer_board1[2:4, :, :])
        queen = 9 * np.sum(layer_board1[4, :, :])

        maxscore = 40
        material = pawns + rooks + minor + queen
        board_value = self.color * material / maxscore
        if noise:
            added_noise = np.random.randn() / 1e3
        return board_value + added_noise

    def select_move(self, moves, successor_values):
        successor_values = np.array(successor_values) * self.color
        return moves[np.argmax(successor_values)]


class NeuralNetworkAgent(object):

    def __init__(self, lr=0.003, color=1):
        self.color = color
        self.optimizer = Adam(lr=lr)
        self.model = Model()
        self.proportional_error = False
        self.init_network()

    def fix_model(self):
        """
        The fixed model is the model used for bootstrapping
        Returns:
        """

        self.fixed_model = clone_model(self.model)
        self.fixed_model.compile(optimizer=self.optimizer, loss='mse', metrics=['mse'])
        self.fixed_model.set_weights(self.model.get_weights())

    def init_network(self):
        layer_state = Input(shape=(8, 8, 8), name='state')

        openfile = Conv2D(3, (8, 1), padding='valid', activation=LeakyReLU(alpha=0.1), name='fileconv')(
            layer_state)  # 3,8,1
        openrank = Conv2D(3, (1, 8), padding='valid', activation=LeakyReLU(alpha=0.1), name='rankconv')(
            layer_state)  # 3,1,8
        quarters = Conv2D(3, (4, 4), padding='valid', activation=LeakyReLU(alpha=0.1), name='quarterconv',
                          strides=(4, 4))(
            layer_state)  # 3,2,2
        large = Conv2D(8, (6, 6), padding='valid', activation=LeakyReLU(alpha=0.1), name='largeconv')(
            layer_state)  # 8,2,2

        board1 = Conv2D(16, (3, 3), padding='valid', activation=LeakyReLU(alpha=0.1), name='board1')(
            layer_state)  # 16,6,6
        board2 = Conv2D(20, (3, 3), padding='valid', activation=LeakyReLU(alpha=0.1), name='board2')(board1)  # 20,4,4
        board3 = Conv2D(24, (3, 3), padding='valid', activation=LeakyReLU(alpha=0.1), name='board3')(board2)  # 24,2,2

        flat_file = Flatten()(openfile)
        flat_rank = Flatten()(openrank)
        flat_quarters = Flatten()(quarters)
        flat_large = Flatten()(large)

        flat_board = Flatten()(board1)
        flat_board3 = Flatten()(board3)

        dense1 = Concatenate(name='dense_bass')(
            [flat_file, flat_rank, flat_quarters, flat_large, flat_board, flat_board3])
        dropout1 = Dropout(rate=0.1)(dense1)
        dense2 = Dense(128, activation='sigmoid')(dropout1)
        dense3 = Dense(64, activation='sigmoid')(dense2)
        dropout3 = Dropout(rate=0.1)(dense3, training=True)
        dense4 = Dense(32, activation='sigmoid')(dropout3)
        dropout4 = Dropout(rate=0.1)(dense4, training=True)

        value_head = Dense(1)(dropout4)
        self.model = Model(inputs=layer_state,
                           outputs=[value_head])
        self.model.compile(optimizer=self.optimizer,
                           loss=[mean_squared_error]
                           )

    def predict(self, board_layer):
        return self.model.predict(board_layer)

    def TD_update(self, states, rewards, sucstates, episode_active, gamma=0.9):
        """
        Update the SARSA-network using samples from the minibatch
        Args:
            minibatch: list
                The minibatch contains the states, moves, rewards and new states.

        Returns:
            td_errors: np.array
                array of temporal difference errors

        """
        suc_state_values = self.fixed_model.predict(sucstates)
        V_target = np.array(rewards) + np.array(episode_active) * gamma * np.squeeze(suc_state_values)
        # Perform a step of minibatch Gradient Descent.
        self.model.fit(x=states, y=V_target, epochs=1, verbose=0)

        V_state = self.model.predict(states)  # the expected future returns
        td_errors = V_target - np.squeeze(V_state)

        return td_errors

    def MC_update(self, states, returns):
        """
        Update network using a monte carlo playout
        Args:
            states: starting states
            returns: discounted future rewards

        Returns:
            td_errors: np.array
                array of temporal difference errors
        """
        self.model.fit(x=states, y=returns, epochs=0, verbose=0)
        V_state = np.squeeze(self.model.predict(states))
        td_errors = returns - V_state

        return td_errors

    def select_move(self, moves, successor_values):
        successor_values = self.color * np.array(successor_values)
        move_probas = softmax(successor_values)
        move = np.random.choice(moves, p=move_probas)
        return move
