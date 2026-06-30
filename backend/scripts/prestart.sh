#! /usr/bin/env bash

set -e
set -x

# 等待数据库启动
python app/backend_pre_start.py

# 运行迁移
alembic upgrade head

# 在数据库中创建初始数据
python app/initial_data.py
