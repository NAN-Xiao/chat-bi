#!/bin/bash

ZHISHU_BASE=/opt

read -r -p "即将卸载星通智数服务，包括删除运行目录、数据及相关镜像，是否继续? [Y/n] " input

case $input in
   [yY][eE][sS]|[yY])
      echo "Yes"
      ;;
   [nN][oO]|[nN])
      echo "No"
      exit 1
      ;;
   *)
      echo "无效输入..."
      exit 1
      ;;
esac

echo "停止星通智数服务"
sctl stop >/dev/null 2>&1

if [ -f /usr/bin/sctl ]; then
   # 获取已安装的星通智数运行目录
   ZHISHU_BASE=$(grep "^ZHISHU_BASE=" /usr/bin/sctl | cut -d'=' -f2)
fi

ZHISHU_IMAGE_REPOSITORY=zhishu
if [ -f ${ZHISHU_BASE}/zhishu/.env ]; then
   set -a
   source ${ZHISHU_BASE}/zhishu/.env
   set +a
fi

# 清理星通智数相关镜像
if test ! -z "$(docker images -f dangling=true -q)"; then
   echo "清理虚悬镜像"
   docker rmi $(docker images -f dangling=true -q)
fi

zhishu_images=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -F "${ZHISHU_IMAGE_REPOSITORY}:")
if test -n "$zhishu_images"; then
   echo "清理星通智数镜像"
   echo "$zhishu_images" | xargs -r docker rmi
fi

# 清理星通智数运行目录及命令行工具 sctl
rm -rf ${ZHISHU_BASE}/zhishu /usr/bin/sctl

echo "星通智数服务卸载完成"
