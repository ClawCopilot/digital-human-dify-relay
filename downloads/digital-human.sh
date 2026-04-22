#!/bin/bash

# 回到根路径
cd /
rm -rf /digital-human.rar
rm -rf /digital-human.py
rm -rf /etc/systemd/system/digital-human.service

# apt安装rar和redis-server
sudo apt update
sudo apt install rar redis-server

#启动redis-server，并设置开机自启动 redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# pip安装所需的包
pip install redis fastapi uvicorn -i https://pypi.tuna.tsinghua.edu.cn/simple 

# 从obs桶获取转发服务代码
wget https://documentation-samples.obs.cn-north-4.myhuaweicloud.com/solution-as-code-publicbucket/solution-as-code-moudle/building-a-dify-llm-application-development-platform/human/digital-human.rar
rar x digital-human.rar

# 替换dify对应的url和api key
sed -i "s/<your dify ip>/$1/g" digital-human.py
sed -i "s/<your dify api key>/$2/g" digital-human.py

#启动对接数字人的python服务，并设置开机自启动
mv digital-human.service /etc/systemd/system/digital-human.service
sudo systemctl daemon-reload
sudo systemctl enable digital-human.service
sudo systemctl start digital-human.service

