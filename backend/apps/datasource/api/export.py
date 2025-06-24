# Author: Junjun
# Date: 2025/6/24

import time

from fastapi import APIRouter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from common.core.deps import SessionDep
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

router = APIRouter(tags=["export"], prefix="/export")


@router.get("/png")
async def export(session: SessionDep):


    options = Options()
    options.add_argument("--headless")
    service = Service(executable_path='/root/sqlbot/chromedriver-linux64/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)  # 或者使用webdriver.Firefox()等
    print('init done')
    # 打开网页
    driver.get('https://g2.antv.antgroup.com/examples/general/interval/#bar-basic')
    driver.set_window_size(width=1920, height=1080)

    # 等待页面加载完成（根据需要调整时间）

    try:
        # 等待直到某个元素加载完成，例如某个具体的元素或者某个时间（例如10秒）
        print("started driver")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        time.sleep(2)
    except:
        print("Timeout")

    # 获取整个页面的截图并保存为图片文件
    driver.save_screenshot('screenshot.png')

    # 关闭浏览器
    driver.quit()
