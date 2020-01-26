# Deep Learning Template Project

This is my template project for deep learning.

Features

* Explicit Pytorch style main loop (if you know Pytorch you can read the main loop)
* Convention over configuration management from yaml files and command line
* Simple checkpoint and restore system
* Simple dataset management
* DL Network blocks configured by both strings and modules
* Tensorboard logging
* Real time visualization of layers and outputs during training

### Basic command usage
```commandline
train.py --config config/cifar10.yaml --display 10
```
Train an autoencoder on cifar10, displaying images every 10 batches

```commandline
train.py --config config/cifar10.yaml --display 10 --batchsize 64  --epochs 200 
```
Train an autoencoder on cifar10, with batch size 64 and for 200 passes through the training set

### Configuration

Configuration flags can be specified in argparse parameters, or in yaml files, or in both.

Precedents is
* Arguments from command line
* Arguments from the config file
* Default value if specified in config.py

Yaml files can contain nested name-value pairs and they will be flattened as below...

```yaml
dataset:
  name: celeba
  train_len: 10000
  test_len: 1000
  
```

will be flattened to argparse arguments as below

```
--dataset_name celeba
--dataset_train_len 10000
--dataset_test_len: 1000
```

### Data package

A data package is an object that contains everything required to load the data for training.

```python
import datasets.package as package

datapack = package.datasets['celeba']

train, test = datapack.make(train_len=10000, test_len=400, data_root='data')

``` 

get a training set of length 1000 and a test set of length 400