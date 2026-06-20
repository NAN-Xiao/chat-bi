#!/bin/bash

INSTALL_TYPE='install'
title_count=1

CURRENT_DIR=$(
    cd "$(dirname "$0")"
    pwd
)

function log() {
    echo -e "${1}" 2>&1 | tee -a ${CURRENT_DIR}/install.log
}

function log_title () {
    log "${title_count}. ${1}"
    let title_count++
}

function log_content () {
    log "\t${1}"
}

function check_and_prepare_env_params() {
    log "当前时间 : $(date)"
    log_title "检查安装环境并初始化环境变量"

    cd ${CURRENT_DIR}
    if [ -f /usr/bin/sctl ]; then
        echo "当前版本： $(sctl version | head -n 1)"

        # 获取已安装的星通智数运行目录
        ZHISHU_BASE=$(grep "^ZHISHU_BASE=" /usr/bin/sctl | cut -d'=' -f2)
        ZHISHU_BASE_OLD=${ZHISHU_BASE}
        sed -i -e "s#ZHISHU_BASE=.*#ZHISHU_BASE=${ZHISHU_BASE}#g" sctl
        \cp sctl /usr/local/bin && chmod +x /usr/local/bin/sctl

        log_content "停止星通智数服务"
        sctl stop

        INSTALL_TYPE='upgrade'
    fi

    set -a
    source ${CURRENT_DIR}/install.conf
    if [[ ${ZHISHU_BASE_OLD} ]];then
        ZHISHU_BASE=${ZHISHU_BASE_OLD}
        export ZHISHU_BASE=${ZHISHU_BASE_OLD}
    fi
    if [[ -d ${ZHISHU_BASE} ]] && [[ -f ${ZHISHU_BASE}/zhishu/.env ]]; then
        source $ZHISHU_BASE/zhishu/.env
        INSTALL_TYPE='upgrade'
        log_content "升级安装"
    else
        INSTALL_TYPE='install'
        mkdir -p ${ZHISHU_BASE}
        log_content "全新安装"
    fi
    set +a
}

function set_run_base_path() {
    log_title "设置运行目录"
    ZHISHU_RUN_BASE=$ZHISHU_BASE/zhishu
    CONF_FOLDER=${ZHISHU_RUN_BASE}/conf
    TEMPLATES_FOLDER=${ZHISHU_RUN_BASE}/templates
    log_content "运行目录 $ZHISHU_RUN_BASE"
    log_content "配置文件目录 $CONF_FOLDER"
}

function prepare_zhishu_run_base() {
    log_title "初始化运行目录"
    cd ${CURRENT_DIR}
    mkdir -p ${ZHISHU_RUN_BASE}
    log_content "复制安装文件到运行目录"
    cp -r ./zhishu/* ${ZHISHU_RUN_BASE}/

    cd ${ZHISHU_RUN_BASE}
    env | grep ZHISHU_ >.env

    mkdir -p ${ZHISHU_RUN_BASE}/conf
    mkdir -p ${ZHISHU_RUN_BASE}/data/zhishu/{excel,images,logs}

    if [ "${ZHISHU_EXTERNAL_DB}" = "false" ]; then
        mkdir -p ${ZHISHU_RUN_BASE}/data/postgresql
        export ZHISHU_DB_PORT=5432
    else
        sed -i -e "/^    depends_on/,+2d" docker-compose.yml
    fi

    log_content "调整配置文件参数"
    cd ${ZHISHU_RUN_BASE}
    cp -r ${TEMPLATES_FOLDER}/* ${CONF_FOLDER}

    cd ${TEMPLATES_FOLDER}
    templates_files=( zhishu.conf )
    for i in ${templates_files[@]}; do
       if [ -f $i ]; then
           envsubst < $i > ${CONF_FOLDER}/$i
       fi
    done
}

function update_sctl() {
    log_title "安装 sctl 命令行工具"
    log_content "安装至 /usr/local/bin/sctl & /usr/bin/sctl"
    cd ${CURRENT_DIR}
    sed -i -e "s#ZHISHU_BASE=.*#ZHISHU_BASE=${ZHISHU_BASE}#g" sctl
    \cp sctl /usr/local/bin && chmod +x /usr/local/bin/sctl
    if [ ! -f /usr/bin/sctl ]; then
        ln -s /usr/local/bin/sctl /usr/bin/sctl 2>/dev/null
    fi
}

function prepare_system_settings() {
    log_title "修改操作系统相关设置"
    if which getenforce >/dev/null 2>&1 && [ $(getenforce) == "Enforcing" ];then
        log_content  "关闭 SELINUX"
        setenforce 0
        sed -i "s/SELINUX=enforcing/SELINUX=disabled/g" /etc/selinux/config
    fi

    if which firewall-cmd >/dev/null 2>&1; then
        if systemctl is-active firewalld &>/dev/null ;then
            log_content "开启防火墙端口 ${ZHISHU_WEB_PORT}"
            firewall-cmd --zone=public --add-port=${ZHISHU_WEB_PORT}/tcp --permanent
            log_content "开启防火墙端口 ${ZHISHU_MCP_PORT}"
            firewall-cmd --zone=public --add-port=${ZHISHU_MCP_PORT}/tcp --permanent
            firewall-cmd --reload
        else
            log_content "防火墙未开启，忽略端口开放"
        fi
    fi
}

function install_docker() {
    log_title "安装 docker"
    #Install docker
    ##Install Latest Stable Docker Release
    cd ${CURRENT_DIR}

    if which docker >/dev/null 2>&1; then
        log_content "检测到 Docker 已安装，跳过安装步骤"
        log_content "启动 Docker "
        service docker start >/dev/null 2>&1 | tee -a ${CURRENT_DIR}/install.log
    else
       if [[ -d docker ]]; then
           log_content "离线安装 docker"
           cp docker/bin/* /usr/bin/
           cp docker/service/docker.service /etc/systemd/system/
           chmod +x /usr/bin/docker*
           chmod 644 /etc/systemd/system/docker.service
       else
           log_content "在线安装 docker"
           if [[ -z "${DOCKER_INSTALL_SCRIPT_URL}" ]]; then
              log_content "未配置 DOCKER_INSTALL_SCRIPT_URL，无法在线安装 Docker"
              exit 1
           fi
           curl -fsSL "${DOCKER_INSTALL_SCRIPT_URL}" -o get-docker.sh 2>&1 | tee -a ${CURRENT_DIR}/install.log
           if [[ ! -f get-docker.sh ]];then
              log_content "docker 在线安装脚本下载失败，请稍候重试"
              exit 1
           fi
           sudo sh get-docker.sh 2>&1 | tee -a ${CURRENT_DIR}/install.log
       fi

       docker_config_folder="/etc/docker"
       if [ ! -d "$docker_config_folder" ];then
           mkdir -p "$docker_config_folder"
           cat <<EOF> $docker_config_folder/daemon.json
           {
              "log-driver": "json-file",
              "log-opts": {
                  "max-file": "3",
                  "max-size": "10m"
              }
           }
EOF
       fi

       log_content "启动 docker"
       systemctl enable docker >/dev/null 2>&1; systemctl daemon-reload; systemctl start docker 2>&1 | tee -a ${CURRENT_DIR}/install.log

       docker version >/dev/null 2>&1
       if [ $? -ne 0 ]; then
           log_content "docker 安装失败"
           exit 1
       else
           log_content "docker 安装成功"

       fi
    fi
}

function install_docker_compose() {
    log_title "安装 docker-compose"
    #Install docker-compose
    cd ${CURRENT_DIR}
    ##Install Latest Stable Docker Compose Release
    docker-compose version >/dev/null 2>&1
    if [ $? -ne 0 ]; then
       docker compose version >/dev/null 2>&1
       if [ $? -eq 0 ]; then
           echo 'docker compose "$@"' > /usr/bin/docker-compose
           chmod +x /usr/bin/docker-compose
       else
           if [[ -d docker ]]; then
              log_content "离线安装 docker-compose"
              cp docker/bin/docker-compose /usr/bin/
              chmod +x /usr/bin/docker-compose
           else
              log_content "在线安装 docker-compose"
              if [[ -z "${DOCKER_COMPOSE_DOWNLOAD_URL}" ]]; then
                 log_content "未配置 DOCKER_COMPOSE_DOWNLOAD_URL，无法在线安装 Docker Compose"
                 exit 1
              fi
              curl -L "${DOCKER_COMPOSE_DOWNLOAD_URL}" -o /usr/local/bin/docker-compose 2>&1 | tee -a ${CURRENT_DIR}/install.log
              if [[ ! -f /usr/local/bin/docker-compose ]];then
                  log_content "docker-compose 下载失败，请稍候重试"
                  exit 1
              fi
              chmod +x /usr/local/bin/docker-compose
              ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
           fi
       fi

       docker-compose version >/dev/null
       if [ $? -ne 0 ]; then
           log_content "docker-compose 安装失败"
           exit 1
       else
           log_content "docker-compose 安装成功"
       fi
    else
       log_content "检测到 Docker Compose 已安装，跳过安装步骤"
    fi
    export COMPOSE_HTTP_TIMEOUT=180
}

function load_images() {
    log_title "加载星通智数镜像"
    cd ${CURRENT_DIR}

    for i in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "${ZHISHU_IMAGE_REPOSITORY_PATTERN:-chat-bi|zhishu}"); do
       current_images[${#current_images[@]}]=${i##*/}
    done

    # 加载镜像
    if [[ -d images ]]; then
       for i in $(ls images); do
           if [[ "${current_images[@]}"  =~ "${i%.tar.gz}" ]]; then
              log_content "已存在镜像 ${i%.tar.gz}"
           else
              log_content "加载镜像 ${i%.tar.gz}"
              docker load -i images/$i >/dev/null 2>&1 | tee -a ${CURRENT_DIR}/install.log
           fi
       done
    else
       log_content "未发现离线 images 目录，跳过镜像预加载"
    fi
}

function start_zhishu() {
    log_title "启动星通智数服务"
    sctl reload 2>&1 | tee -a ${CURRENT_DIR}/install.log
    if [[ $? -ne 0 ]]; then
        log_content "星通智数服务启动失败，请检查日志"
        exit 1
    fi
    echo
    if [[ $INSTALL_TYPE != "upgrade" ]];then
       echo -e "======================= 安装完成 =======================\n" 2>&1 | tee -a ${CURRENT_DIR}/install.log
       echo -e "系统登录信息如下:\n\t访问地址: http://服务器IP:$ZHISHU_WEB_PORT\n\t用户名: admin\n\t初始密码: elex@123" 2>&1 | tee -a ${CURRENT_DIR}/install.log
    else
       echo -e "======================= 升级完成 =======================\n" 2>&1 | tee -a ${CURRENT_DIR}/install.log
    fi
}

function main() {
    check_and_prepare_env_params
    set_run_base_path
    prepare_zhishu_run_base
    update_sctl
    prepare_system_settings
    install_docker
    install_docker_compose
    load_images
    start_zhishu
}

main
