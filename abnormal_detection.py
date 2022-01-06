import pandas as pd
import numpy as np
import math
from math import sqrt
import os
import csv
from keras.models import Sequential, Model
from keras.layers import Lambda, Activation, Input, Dense, Dropout, SimpleRNN, Flatten, \
    LSTM, GRU, Bidirectional, Layer, Permute, Reshape, Multiply, RepeatVector, Dot, Concatenate, merge
from keras import optimizers
import keras.backend as K
from sklearn.preprocessing import MinMaxScaler
from matplotlib import pyplot as plt
from sklearn.metrics import mean_squared_error
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_absolute_percentage_error
from sklearn.metrics import r2_score
from statsmodels.tsa.arima_model import ARIMA
from statsmodels.tsa.vector_ar.var_model import VAR
from sklearn.svm import SVR
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
import tensorflow
import numpy.linalg as la
import time
tensorflow.random.set_seed(2)

exchanges = ["binance", "coinbase", "huobi", "kraken", "kucoin"]

class Attention(Layer):

    def __init__(self, units=128, **kwargs):
        self.units = units
        super().__init__(**kwargs)

    def __call__(self, inputs):
        """
        Many-to-one attention mechanism for Keras.
        @param inputs: 3D tensor with shape (batch_size, time_steps, input_dim).
        @return: 2D tensor with shape (batch_size, 128)
        @author: felixhao28, philipperemy.
        """
        hidden_states = inputs
        hidden_size = int(hidden_states.shape[2])
        # Inside dense layer
        #              hidden_states            dot               W            =>           score_first_part
        # (batch_size, time_steps, hidden_size) dot (hidden_size, hidden_size) => (batch_size, time_steps, hidden_size)
        # W is the trainable weight matrix of attention Luong's multiplicative style score
        score_first_part = Dense(hidden_size, use_bias=False, name='attention_score_vec')(hidden_states)
        #            score_first_part           dot        last_hidden_state     => attention_weights
        # (batch_size, time_steps, hidden_size) dot   (batch_size, hidden_size)  => (batch_size, time_steps)
        h_t = Lambda(lambda x: x[:, -1, :], output_shape=(hidden_size,), name='last_hidden_state')(hidden_states)
        score = Dot(axes=[1, 2], name='attention_score')([h_t, score_first_part])
        attention_weights = Activation('softmax', name='attention_weight')(score)
        # (batch_size, time_steps, hidden_size) dot (batch_size, time_steps) => (batch_size, hidden_size)
        context_vector = Dot(axes=[1, 1], name='context_vector')([hidden_states, attention_weights])
        pre_activation = Concatenate(name='attention_output')([context_vector, h_t])
        attention_vector = Dense(self.units, use_bias=False, activation='tanh', name='attention_vector')(pre_activation)
        return attention_vector

    def get_config(self):
        return {'units': self.units}

    @classmethod
    def from_config(cls, config):
        return cls(**config)

class attention(Layer):
    def __init__(self,**kwargs):
        super(attention,self).__init__(**kwargs)

    def build(self,input_shape):
        self.W=self.add_weight(name="att_weight",shape=(input_shape[-1],1),initializer="normal")
        self.b=self.add_weight(name="att_bias",shape=(input_shape[1],1),initializer="zeros")
        super(attention, self).build(input_shape)

    def call(self,x):
        et=K.squeeze(K.tanh(K.dot(x,self.W)+self.b),axis=-1)
        at=K.softmax(et)
        at=K.expand_dims(at,axis=-1)
        output=x*at
        return K.sum(output,axis=1)

    def compute_output_shape(self,input_shape):
        return (input_shape[0],input_shape[-1])

    def get_config(self):
        return super(attention,self).get_config()


def model_lstm_att(time_steps, input_dim, n_units):
    K.clear_session()  # 清除之前的模型，省得压满内存
    model_input = Input(shape=(time_steps, input_dim))
    x = LSTM(n_units, return_sequences=True)(model_input)
    x = attention()(x)
    x = Dense(1)(x)
    model = Model(model_input, x)
    return model
def model_lstm(seq_len, n_features, n_units):
    model = Sequential()
    model.add(LSTM(n_units, activation="relu", input_shape=(seq_len, n_features)))
    model.add(Dense(1))
    return model

def evaluation(real, pre):
    rmse = mean_squared_error(real, pre, squared=False)
    mae = mean_absolute_error(real, pre)
    mape = mean_absolute_percentage_error(real, pre)
    r2 = r2_score(real, pre)
    var = 1-(np.var(real - pre))/np.var(real)
    F_norm = la.norm(real-pre)/la.norm(real)

    return rmse, mae, mape, r2, var, 1-F_norm

def min_max_scaler(li):
    min_ = min(li)
    max_ = max(li)
    ret = [(i - min_) / (max_ - min_) for i in li]
    return ret, min_, max_

def data_split(data, train_rate, seq_len, pre_len=1):
    time_len, n_feature = data.shape
    train_size = int(time_len * train_rate)
    train_data = data[0:train_size]
    trainX, trainY, testX, testY = [], [], [], []
    for i in range(train_size-seq_len-pre_len):
        a = train_data[i: i + seq_len + pre_len]
        trainX.append(a[0: seq_len])
        trainY.append(a[seq_len: seq_len + pre_len, 0])
    for i in range(train_size-seq_len-pre_len, time_len-pre_len-seq_len):
        b = data[i: i+seq_len+pre_len,:]
        testX.append(b[0:seq_len])
        testY.append(b[seq_len:seq_len+pre_len, 0])
    trainX1 = np.array(trainX)
    trainY1 = np.array(trainY)
    testX1 = np.array(testX)
    testY1 = np.array(testY)
    return trainX1, trainY1, testX1, testY1

def lstm(n_units=64, seq_len=10, batch_size=64):
    error_list = []

    rmse_list = []
    mae_list = []
    mape_list = []
    for i in range(len(exchanges)):
        exchange = exchanges[i]
        important = True
        if important:
            file = open('./exchange/feature/' + exchange + '_ft.csv')
        else:
            file = open('./exchange/feature/' + exchange + '_ft_not_important.csv')
        df = pd.read_csv(file)

        data = df.values
        print("type data")
        print(type(data))
        time_len, n_features = data.shape
        train_rate = 0.8
        train_size = int(time_len*train_rate)
        trainX, trainY, testX, testY = data_split(data, train_rate=train_rate, seq_len=seq_len)
        scaled_data = data.copy()
        # 对每一列特征进行归一化
        scaler = []
        for j in range(n_features):
            temp_scaler = MinMaxScaler(feature_range=(0, 1))
            temp = temp_scaler.fit_transform(np.array(scaled_data[:, j]).reshape(-1,1))
            scaler.append(temp_scaler)
            temp = temp.reshape(-1)
            scaled_data[:, j] = temp
        trainX1, trainY1, testX1, testY1 = data_split(scaled_data, train_rate=train_rate, seq_len=seq_len)

        model_name = "LSTM_attention"
        if model_name=="LSTM_attention":
            model = model_lstm_att(seq_len, n_features, n_units)
        if model_name=="LSTM":
            model = model_lstm(seq_len, n_features, n_units)

        opt = optimizers.Adam()
        model.compile(optimizer=opt, loss='mse')
        history = model.fit(trainX1, trainY1, epochs=50, batch_size=batch_size, validation_data=(testX1, testY1), verbose=2, shuffle=False)
        # 绘制历史数据
        if False:
            plt.figure(figsize=(10, 5))
            plt.grid(linestyle="--")
            plt.plot(history.history['loss'], label='train')
            plt.plot(history.history['val_loss'], label='test')
            plt.legend()
            plt.title(exchange)
            plt.savefig('./exchange/figure/lstm_prediction' + exchange + '_' + model_name + '_loss.png')
            plt.show()
        prediction_val = model.predict(testX1)
        print(type(prediction_val))
        print(prediction_val)

        rmse, mae, mape, r2, var, _ = evaluation(testY1, prediction_val)
        print("rmse = {}\nmae = {}\nmape = {}\nr2 = {}\nvar = {}\n".format(rmse, mae, mape, r2, var))
        error_list.append("rmse = {}\nmae = {}\nmape = {}\n".format(rmse, mae, mape))

        rmse_list.append(rmse)
        mae_list.append(mae)
        mape_list.append(mape)

        prediction_val = np.array(scaled_data[0:train_size, 0].tolist()+prediction_val[:, 0].tolist())
        prediction_val = prediction_val.reshape(-1,1)
        prediction_val = scaler[0].inverse_transform(prediction_val)
        prediction_val = prediction_val[train_size:,0]
        print("testY")
        testY = testY[:,0]
        print("testY.shape")
        print(testY.shape)
        print(type(testY))
        print("prediction_val")
        print(prediction_val.shape)
        print(type(prediction_val))

        if True:
            plt.figure(figsize=(10, 5))
            plt.grid(linestyle="--")
            plt.plot(range(time_len-train_size), testY)
            plt.plot(range(time_len-train_size), np.array(prediction_val))
            upper_bound = [it + 3 * np.std(testY) for it in prediction_val]
            lower_bound = [it - 3 * np.std(testY) for it in prediction_val]
            abnormal_x = []
            abnormal_y = []
            for j in range(len(upper_bound)):
                if testY[j]>upper_bound[j]:
                    abnormal_x.append(j)
                    abnormal_y.append(testY[j])
            print(exchange)
            print("abnormal_x")
            print(abnormal_x)
            print("abnormal_y")
            print(abnormal_y)
            print("train_size+x")
            print([it+train_size for it in abnormal_x])
            plt.plot(range(time_len-train_size), upper_bound, "--")
            plt.plot(range(time_len-train_size), lower_bound, "--")
            plt.scatter(abnormal_x, abnormal_y, c="r", marker="x")
            plt.legend(("real", model_name, "upper_bound", "lower_bound", "abnormal_detected"), loc=2)
            plt.title(exchange)
            plt.xlabel("Days")
            plt.ylabel("Transaction Amount(USD)")
            plt.savefig('./exchange/figure/lstm_prediction_' + exchange + '_' + model_name + '_prediction.png')
            plt.show()
    for i in range(len(exchanges)):
        print(exchanges[i])
        print(error_list[i])
    return rmse_list, mae_list, mape_list

def parameter_sensitivity(parameter, para_range):
    rmse_list = [[] for i in range(len(exchanges))] #第一维表示不同交易所，第二位表示不同的参数对应的值
    mae_list = [[] for i in range(len(exchanges))]
    mape_list = [[] for i in range(len(exchanges))]
    for it in para_range:
        if parameter=="n_units":
            temp_rmse, temp_mae, temp_mape = lstm(n_units=it)
        if parameter=="seq_len":
            temp_rmse, temp_mae, temp_mape = lstm(seq_len=it)
        if parameter == "batch_size":
            temp_rmse, temp_mae, temp_mape = lstm(batch_size=it)
        for jj in range(len(temp_rmse)):
            rmse_list[jj].append(temp_rmse[jj])
            mae_list[jj].append(temp_mae[jj])
            mape_list[jj].append(temp_mape[jj])
    for i in range(len(exchanges)):
        exchange = exchanges[i]
        rmse_list[i],_,_ = min_max_scaler(rmse_list[i])
        mae_list[i],_,_ = min_max_scaler(mae_list[i])
        mape_list[i],_,_ = min_max_scaler(mape_list[i])
        plt.figure()
        plt.grid(linestyle="--")
        plt.plot(para_range, rmse_list[i])
        plt.plot(para_range, mae_list[i])
        plt.plot(para_range, mape_list[i])
        plt.legend(("RMSE", "MAE", "MAPE"))
        plt.xlabel(parameter)
        plt.ylabel("Normalised Values")
        plt.title(exchange)
        plt.savefig('./exchange/figure/para_' + parameter + '_' + exchange + '.png')
        plt.show()

def cal_date():
    li = []
    li.append([1400, 1415, 1416, 1420, 1421, 1543])
    li.append([222])
    li.append([1413, 1450, 1501])
    li.append([2097, 2111, 2113])
    li.append([1463, 1503, 1522, 1542])
    start_time = [1499212800, 1619481600, 1495497600, 1438905600, 1505606400]
    for i in range(len(li)):
        print(exchanges[i])
        for j in range(len(li[i])):
            temp_time = start_time[i] + li[i][j]*86400
            timeArray = time.localtime(temp_time)
            otherStyleTime = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)
            print(otherStyleTime)

if __name__=='__main__':
    lstm()
    # parameter_sensitivity("seq_len", [5, 10, 20, 40, 80])
    # cal_date()