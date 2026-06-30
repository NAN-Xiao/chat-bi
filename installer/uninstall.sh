#!/bin/bash

SHUZHI_BASE=/opt

read -r -p "即将卸载星通数智服务，包括删除运行目录、数据及相关镜像，是否继续? [Y/n] " input

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

echo "停止星通数智服务"
sctl stop >/dev/null 2>&1

if [ -f /usr/bin/sctl ]; then
   # 获取已安装的星通数智运行目录
   SHUZHI_BASE=$(grep "^SHUZHI_BASE=" /usr/bin/sctl | cut -d'=' -f2)
fi

SHUZHI_IMAGE_REPOSITORY=shuzhi
if [ -f ${SHUZHI_BASE}/shuzhi/.env ]; then
   set -a
   source ${SHUZHI_BASE}/shuzhi/.env
   set +a
fi

# 清理星通数智相关镜像
if test ! -z "$(docker images -f dangling=true -q)"; then
   echo "清理虚悬镜像"
   docker rmi $(docker images -f dangling=true -q)
fi

shuzhi_images=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -F "${SHUZHI_IMAGE_REPOSITORY}:")
if test -n "$shuzhi_images"; then
   echo "清理星通数智镜像"
   echo "$shuzhi_images" | xargs -r docker rmi
fi

# 清理星通数智运行目录及命令行工具 sctl
rm -rf ${SHUZHI_BASE}/shuzhi /usr/bin/sctl

echo "星通数智服务卸载完成"
