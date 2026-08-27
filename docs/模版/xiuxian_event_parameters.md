# 修仙项目事件与事件参数说明

> 本文根据《修仙项目-BI打点整理 (1).xlsx》的“前端”和“后端”工作表重新生成。每个事件参数均按事件表 `event` 的 `personal` JSON 字段配置来源字段、JSONPath 和生成字段名；验收状态、问题状态和内部处理备注不作为知识口径。

## 事件：Launch

**事件说明**

- 展示名称：游戏启动
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

**参数：width**

- 展示名称：分辨率宽
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.width
- 生成字段名：personal.width
- 说明：分辨率宽
- 原始数据类型：int
- 参数备注：中台SDK已有

**参数：height**

- 展示名称：分辨率高
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.height
- 生成字段名：personal.height
- 说明：分辨率高
- 原始数据类型：int
- 参数备注：中台SDK已有

**参数：memorySize**

- 展示名称：设备总内存
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.memorySize
- 生成字段名：personal.memorySize
- 说明：设备总内存
- 原始数据类型：int
- 参数备注：中台SDK已有

**参数：memory_current**

- 展示名称：可用内存
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.memory_current
- 生成字段名：personal.memory_current
- 说明：可用内存
- 原始数据类型：int
- 参数备注：中台SDK已有

## 事件：LoadingStart

**事件说明**

- 展示名称：Loading开始
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

## 事件：LaunchVersion

**事件说明**

- 展示名称：【2】WerbServer请求游戏版本信息
- 事件分类：加载过程
- 事件来源：前端
- 优先级：P2

## 事件：LaunchVersionRet

**事件说明**

- 展示名称：【3】WerbServer平台版本信息返回
- 事件分类：加载过程
- 事件来源：前端
- 优先级：P2

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

## 事件：LoadingFinish

**事件说明**

- 展示名称：Loading结束
- 事件分类：表格未注明
- 事件来源：前端
- 优先级：表格未注明

**参数：loading_costtime**

- 展示名称：耗时
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.loading_costtime
- 生成字段名：personal.loading_costtime
- 说明：耗时
- 原始数据类型：int
- 参数备注：loading完成时间减去开始时间，单位为毫秒，检查设备性能与留存的相关性

## 事件：EPSDKLogin

**事件说明**

- 展示名称：【1】EPSDK 登录
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

## 事件：GameServerLogin

**事件说明**

- 展示名称：【4】请求登录游戏服
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID

## 事件：GameServerLoginRet

**事件说明**

- 展示名称：【5】登录游戏服返回
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_isSuccess**

- 展示名称：返回结果
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isSuccess
- 生成字段名：personal.ed_isSuccess
- 说明：返回结果
- 原始数据类型：bool
- 参数备注：true/flase 成功/失败

## 事件：EnterGame

**事件说明**

- 展示名称：【6】进入游戏
- 事件分类：加载过程
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_isSuccess**

- 展示名称：返回结果
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isSuccess
- 生成字段名：personal.ed_isSuccess
- 说明：返回结果
- 原始数据类型：bool
- 参数备注：true/false 成功/失败

## 事件：NewUserGuideStart

**事件说明**

- 展示名称：新手引导开始
- 事件分类：新手引导
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guideId**

- 展示名称：引导步骤ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guideId
- 生成字段名：personal.ed_guideId
- 说明：引导步骤ID
- 原始数据类型：int

## 事件：NewUserGuide

**事件说明**

- 展示名称：新手引导结束
- 事件分类：新手引导
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guideId**

- 展示名称：引导步骤ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guideId
- 生成字段名：personal.ed_guideId
- 说明：引导步骤ID
- 原始数据类型：int

## 事件：Pinglog

**事件说明**

- 展示名称：客户端ping
- 事件分类：UI界面
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：MaxPing**

- 展示名称：最大ping
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.MaxPing
- 生成字段名：personal.MaxPing
- 说明：最大ping
- 原始数据类型：int
- 参数备注：单位：毫秒

**参数：MinPing**

- 展示名称：最小ping
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.MinPing
- 生成字段名：personal.MinPing
- 说明：最小ping
- 原始数据类型：int
- 参数备注：毫秒

**参数：AvgPing**

- 展示名称：平均ping值
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.AvgPing
- 生成字段名：personal.AvgPing
- 说明：平均ping值
- 原始数据类型：float
- 参数备注：毫秒 当前1次跟前4次取平均值

**参数：MaxFps**

- 展示名称：最大fps
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.MaxFps
- 生成字段名：personal.MaxFps
- 说明：最大fps
- 原始数据类型：int

**参数：MinFps**

- 展示名称：最小fps
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.MinFps
- 生成字段名：personal.MinFps
- 说明：最小fps
- 原始数据类型：int

**参数：AvgFps**

- 展示名称：平均fps
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.AvgFps
- 生成字段名：personal.AvgFps
- 说明：平均fps
- 原始数据类型：float
- 参数备注：当前1次和前9次取平均值

## 事件：PopupShow

**事件说明**

- 展示名称：展示面板
- 事件分类：UI界面
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_popupSource**

- 展示名称：页面跳转来源
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupSource
- 生成字段名：personal.ed_popupSource
- 说明：页面跳转来源
- 原始数据类型：string
- 参数备注：默认主页面，其他为来源页面

**参数：ed_pupupType**

- 展示名称：页面类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_pupupType
- 生成字段名：personal.ed_pupupType
- 说明：页面类型
- 原始数据类型：string
- 参数备注：（该字段暂时不传）

**参数：ed_isActive**

- 展示名称：是否主动触发
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isActive
- 生成字段名：personal.ed_isActive
- 说明：是否主动触发
- 原始数据类型：bool
- 参数备注：true/flase 是/否

**参数：ed_popupExplain**

- 展示名称：面板参数说明
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupExplain
- 生成字段名：personal.ed_popupExplain
- 说明：面板参数说明
- 原始数据类型：string
- 参数备注：如： 1000103 礼包ID（该字段暂时不传）

**参数：ed_popupName**

- 展示名称：面板名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupName
- 生成字段名：personal.ed_popupName
- 说明：面板名称
- 原始数据类型：string
- 参数备注：如：GiftCommonDetailPopupPanel 礼包详情界面

## 事件：PopupClick

**事件说明**

- 展示名称：点击面板
- 事件分类：UI界面
- 事件来源：前端
- 优先级：P2

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_buttonName**

- 展示名称：按钮名称///[路径]
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buttonName
- 生成字段名：personal.ed_buttonName
- 说明：按钮名称///[路径]
- 原始数据类型：string

**参数：ed_popupExplain**

- 展示名称：面板参数说明
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupExplain
- 生成字段名：personal.ed_popupExplain
- 说明：面板参数说明
- 原始数据类型：string
- 参数备注：如：1000103 礼包ID（该字段暂时不传）

**参数：ed_popupName**

- 展示名称：面板名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupName
- 生成字段名：personal.ed_popupName
- 说明：面板名称
- 原始数据类型：string
- 参数备注：如：GiftCommonDetailPopupPanel 礼包详情界面

## 事件：PayBuyRet

**事件说明**

- 展示名称：货币购买付款成功
- 事件分类：付费
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：数值

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_popupName**

- 展示名称：面板名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupName
- 生成字段名：personal.ed_popupName
- 说明：面板名称
- 原始数据类型：字符串

**参数：ed_productId**

- 展示名称：礼包id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_productId
- 生成字段名：personal.ed_productId
- 说明：礼包id
- 原始数据类型：字符串
- 参数备注：recharge表的对应id<br>同PayPopup点对应参数的值

**参数：ed_isSuccess**

- 展示名称：返回结果
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isSuccess
- 生成字段名：personal.ed_isSuccess
- 说明：返回结果
- 原始数据类型：布尔值
- 参数备注：true/false 成功/失败

**参数：ed_money**

- 展示名称：金额
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_money
- 生成字段名：personal.ed_money
- 说明：金额
- 原始数据类型：数值
- 参数备注：RMB

**参数：ed_num**

- 展示名称：购买数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_num
- 生成字段名：personal.ed_num
- 说明：购买数量
- 原始数据类型：数值

**参数：ed_orderId**

- 展示名称：订单ID（支付平台）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_orderId
- 生成字段名：personal.ed_orderId
- 说明：订单ID（支付平台）
- 原始数据类型：字符串

**参数：ed_currency**

- 展示名称：货币类型（国际标准货币单位简写，如USD、CNY）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currency
- 生成字段名：personal.ed_currency
- 说明：货币类型（国际标准货币单位简写，如USD、CNY）
- 原始数据类型：字符串
- 参数备注：CNY

**参数：ed_popupId**

- 展示名称：面板唯一ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupId
- 生成字段名：personal.ed_popupId
- 说明：面板唯一ID
- 原始数据类型：字符串
- 参数备注：每次曝光刷新

**参数：ed_localMoney**

- 展示名称：显示的当地支付金额
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_localMoney
- 生成字段名：personal.ed_localMoney
- 说明：显示的当地支付金额
- 原始数据类型：数值

## 事件：SeeVideoPre

**事件说明**

- 展示名称：展示激励视频（打开含有广告按钮的界面）
- 事件分类：展示激励视频
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_type**

- 展示名称：查看激励视频类型（位置点）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_type
- 生成字段名：personal.ed_type
- 说明：查看激励视频类型（位置点）
- 原始数据类型：int
- 参数备注：具体见ed_type枚举

**参数：ed_videoTime**

- 展示名称：视频时长
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_videoTime
- 生成字段名：personal.ed_videoTime
- 说明：视频时长
- 原始数据类型：int
- 参数备注：单位：毫秒

**参数：ed_channel**

- 展示名称：广告渠道
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_channel
- 生成字段名：personal.ed_channel
- 说明：广告渠道
- 原始数据类型：string
- 参数备注：例如 wechat

## 事件：SeeVideo

**事件说明**

- 展示名称：观看激励视频（激励视频弹出来的一瞬间）
- 事件分类：观看激励视频
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_type**

- 展示名称：查看激励视频类型（位置点）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_type
- 生成字段名：personal.ed_type
- 说明：查看激励视频类型（位置点）
- 原始数据类型：int
- 参数备注：具体见ed_type枚举

**参数：ed_videoTime**

- 展示名称：视频时长
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_videoTime
- 生成字段名：personal.ed_videoTime
- 说明：视频时长
- 原始数据类型：int
- 参数备注：单位：毫秒

**参数：ed_channel**

- 展示名称：广告渠道
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_channel
- 生成字段名：personal.ed_channel
- 说明：广告渠道

## 事件：SeeVideoRet

**事件说明**

- 展示名称：观看激励视频返回
- 事件分类：观看激励视频返回
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_type**

- 展示名称：查看激励视频类型（位置点）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_type
- 生成字段名：personal.ed_type
- 说明：查看激励视频类型（位置点）
- 原始数据类型：int
- 参数备注：具体见ed_type枚举

**参数：ed_videoTime**

- 展示名称：视频时长
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_videoTime
- 生成字段名：personal.ed_videoTime
- 说明：视频时长
- 原始数据类型：int
- 参数备注：单位：毫秒

**参数：ed_channel**

- 展示名称：广告渠道
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_channel
- 生成字段名：personal.ed_channel
- 说明：广告渠道

**参数：ed_isSuccess**

- 展示名称：返回结果
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isSuccess
- 生成字段名：personal.ed_isSuccess
- 说明：返回结果
- 原始数据类型：bool
- 参数备注：true/flase 成功/失败

## 事件：ClickVideo

**事件说明**

- 展示名称：点击激励视频（播放视频时）
- 事件分类：点击激励视频
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_type**

- 展示名称：查看激励视频类型（位置点）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_type
- 生成字段名：personal.ed_type
- 说明：查看激励视频类型（位置点）
- 原始数据类型：int
- 参数备注：具体见ed_type枚举

**参数：ed_videoTime**

- 展示名称：视频时长
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_videoTime
- 生成字段名：personal.ed_videoTime
- 说明：视频时长
- 原始数据类型：int
- 参数备注：单位：毫秒

**参数：ed_channel**

- 展示名称：广告渠道
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_channel
- 生成字段名：personal.ed_channel
- 说明：广告渠道

## 事件：ClickAutoAdventure

**事件说明**

- 展示名称：点击自动游历
- 事件分类：点击自动游历
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_clickResult**

- 展示名称：点击后结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_clickResult
- 生成字段名：personal.ed_clickResult
- 说明：点击后结果
- 原始数据类型：int
- 参数备注：1为打开自动游历，2为关闭自动游历

## 事件：ClickTenDraw

**事件说明**

- 展示名称：点击抽卡十连抽
- 事件分类：点击十连抽
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_clickResult**

- 展示名称：点击后结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_clickResult
- 生成字段名：personal.ed_clickResult
- 说明：点击后结果
- 原始数据类型：int
- 参数备注：1为开启十连抽，2为关闭十连抽

## 事件：ClickHumanUp

**事件说明**

- 展示名称：点击自动招募农民
- 事件分类：点击自动招募农民
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_clickResult**

- 展示名称：点击后结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_clickResult
- 生成字段名：personal.ed_clickResult
- 说明：点击后结果
- 原始数据类型：int
- 参数备注：1为开启自动，2为关闭自动

## 事件：ComicPlay

**事件说明**

- 展示名称：漫画播放的起点和终点
- 事件分类：漫画播放
- 事件来源：前端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_comicEnter**

- 展示名称：漫画状态
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_comicEnter
- 生成字段名：personal.ed_comicEnter
- 说明：漫画状态
- 原始数据类型：int
- 参数备注：1为进入，2为完整关闭

## 事件：CreatePlayerClient

**事件说明**

- 展示名称：角色创建
- 事件分类：角色
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_sexType**

- 展示名称：性别选择
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sexType
- 生成字段名：personal.ed_sexType
- 说明：性别选择
- 原始数据类型：int
- 参数备注：1为女，2为男

## 事件：OneClickEquip

**事件说明**

- 展示名称：一键装备
- 事件分类：角色
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：弟子ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：弟子ID
- 原始数据类型：int

## 事件：SpiritualLike

**事件说明**

- 展示名称：灵脉复苏点赞
- 事件分类：角色
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_rankType**

- 展示名称：排行类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_rankType
- 生成字段名：personal.ed_rankType
- 说明：排行类型
- 原始数据类型：int
- 参数备注：rank表id

## 事件：ServerChange

**事件说明**

- 展示名称：切换服务器
- 事件分类：角色
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverNow**

- 展示名称：所选服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverNow
- 生成字段名：personal.ed_serverNow
- 说明：所选服务器ID
- 原始数据类型：int
- 参数备注：切换后的服务器

**参数：ed_serverBefore**

- 展示名称：上一次服务器
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverBefore
- 生成字段名：personal.ed_serverBefore
- 说明：上一次服务器
- 原始数据类型：int
- 参数备注：本次切换前的服务器

## 事件：QiFuAuto

**事件说明**

- 展示名称：祈福自动开关
- 事件分类：祈福
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_qifuAuto**

- 展示名称：祈福自动开关
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuAuto
- 生成字段名：personal.ed_qifuAuto
- 说明：祈福自动开关
- 原始数据类型：int
- 参数备注：1为开始，0为关闭

## 事件：patrolTen

**事件说明**

- 展示名称：十连巡视
- 事件分类：巡视
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_patrolTenOpen**

- 展示名称：十连巡视开关
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_patrolTenOpen
- 生成字段名：personal.ed_patrolTenOpen
- 说明：十连巡视开关
- 原始数据类型：int
- 参数备注：1为打开，0为关闭

## 事件：PayPopup

**事件说明**

- 展示名称：礼包曝光
- 事件分类：付费
- 事件来源：前端
- 优先级：必打点

**参数：ed_popupName**

- 展示名称：面板名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupName
- 生成字段名：personal.ed_popupName
- 说明：面板名称
- 原始数据类型：字符串

**参数：ed_popupId**

- 展示名称：面板唯一ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupId
- 生成字段名：personal.ed_popupId
- 说明：面板唯一ID
- 原始数据类型：字符串
- 参数备注：每次曝光刷新

**参数：ed_productIds**

- 展示名称：礼包id列表
- 数据类型：数组
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_productIds
- 生成字段名：personal.ed_productIds
- 说明：礼包id列表
- 原始数据类型：数组
- 参数备注：['1111', '2222', '3333']

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：数值

## 事件：PayPopupClick

**事件说明**

- 展示名称：点击购买按钮
- 事件分类：付费
- 事件来源：前端
- 优先级：必打点

**参数：ed_popupName**

- 展示名称：面板名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupName
- 生成字段名：personal.ed_popupName
- 说明：面板名称
- 原始数据类型：字符串

**参数：ed_popupId**

- 展示名称：面板唯一ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_popupId
- 生成字段名：personal.ed_popupId
- 说明：面板唯一ID
- 原始数据类型：字符串
- 参数备注：每次曝光刷新

**参数：ed_productId**

- 展示名称：礼包id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_productId
- 生成字段名：personal.ed_productId
- 说明：礼包id
- 原始数据类型：字符串
- 参数备注：同PayPopup点对应参数的值

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：数值

## 事件：FriendAllAdd

**事件说明**

- 展示名称：好友全部添加
- 事件分类：好友
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_friendNum**

- 展示名称：当前好友数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_friendNum
- 生成字段名：personal.ed_friendNum
- 说明：当前好友数量
- 原始数据类型：int

## 事件：FriendAllChange

**事件说明**

- 展示名称：换一批好友
- 事件分类：好友
- 事件来源：前端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_friendNum**

- 展示名称：当前好友数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_friendNum
- 生成字段名：personal.ed_friendNum
- 说明：当前好友数量
- 原始数据类型：int

## 事件：Register

**事件说明**

- 展示名称：注册
- 事件分类：注册
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_existAmount**

- 展示名称：当前角色数量，当前服务器总人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_existAmount
- 生成字段名：personal.ed_existAmount
- 说明：当前角色数量，当前服务器总人数
- 原始数据类型：int

## 事件：Login

**事件说明**

- 展示名称：后端登录
- 事件分类：后端登录
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

## 事件：Logout

**事件说明**

- 展示名称：后端登出
- 事件分类：后端登出
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_playSeconds**

- 展示名称：在线时长
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_playSeconds
- 生成字段名：personal.ed_playSeconds
- 说明：在线时长
- 原始数据类型：int
- 参数备注：单位秒

## 事件：NewUserStep

**事件说明**

- 展示名称：新手引导
- 事件分类：新手引导
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guideGroup**

- 展示名称：引导组ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guideGroup
- 生成字段名：personal.ed_guideGroup
- 说明：引导组ID
- 原始数据类型：string

**参数：ed_guideId**

- 展示名称：引导步骤ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guideId
- 生成字段名：personal.ed_guideId
- 说明：引导步骤ID
- 原始数据类型：string
- 参数备注：后端如无具体步骤id，这可以不记

## 事件：CCU

**事件说明**

- 展示名称：用于计算实时在线人数
- 事件分类：在线人数
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_timestamp**

- 展示名称：计算时间
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_timestamp
- 生成字段名：personal.ed_timestamp
- 说明：计算时间
- 原始数据类型：long
- 参数备注：记录时间戳

**参数：ed_ccu**

- 展示名称：当前在线人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ccu
- 生成字段名：personal.ed_ccu
- 说明：当前在线人数
- 原始数据类型：int

## 事件：ResourceChange

**事件说明**

- 展示名称：资源变动
- 事件分类：资源变化
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_change**

- 展示名称：资源变化量
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_change
- 生成字段名：personal.ed_change
- 说明：资源变化量
- 原始数据类型：object
- 参数备注：{"oil": 10,"gold":10} 对象value为数值类型，具体见【枚举说明】
- 已知子字段映射：
  - oil：JSON路径 `$.ed_change.oil`；生成字段名 `personal.ed_change.oil`
  - gold：JSON路径 `$.ed_change.gold`；生成字段名 `personal.ed_change.gold`

**参数：ed_stock**

- 展示名称：资源存量（变化后）
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_stock
- 生成字段名：personal.ed_stock
- 说明：资源存量（变化后）
- 原始数据类型：object
- 参数备注：{"oil": 10,"gold":10} 对象value为数值类型，具体见【枚举说明】
- 已知子字段映射：
  - oil：JSON路径 `$.ed_stock.oil`；生成字段名 `personal.ed_stock.oil`
  - gold：JSON路径 `$.ed_stock.gold`；生成字段名 `personal.ed_stock.gold`

**参数：ed_targetType**

- 展示名称：作用对象类型（加速的建筑组，造兵的兵种类型）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetType
- 生成字段名：personal.ed_targetType
- 说明：作用对象类型（加速的建筑组，造兵的兵种类型）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_route**

- 展示名称：变化途径（变化原因）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_route
- 生成字段名：personal.ed_route
- 说明：变化途径（变化原因）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_targetId**

- 展示名称：详细原因
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetId
- 生成字段名：personal.ed_targetId
- 说明：详细原因
- 原始数据类型：string
- 参数备注：根据不同途径记录不同内容<br>比如：途径是建筑升级就写建筑ID

## 事件：PreciousChange

**事件说明**

- 展示名称：贵重物品变更
- 事件分类：资源变化
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_itemId**

- 展示名称：变更的贵重物品id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_itemId
- 生成字段名：personal.ed_itemId
- 说明：变更的贵重物品id
- 原始数据类型：int
- 参数备注：item表id

**参数：ed_isAdd**

- 展示名称：是否增加
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_isAdd
- 生成字段名：personal.ed_isAdd
- 说明：是否增加
- 原始数据类型：bool
- 参数备注：true/flase 是/否

**参数：ed_addValue**

- 展示名称：变动数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_addValue
- 生成字段名：personal.ed_addValue
- 说明：变动数量
- 原始数据类型：int
- 参数备注：正是增加，负是消耗

**参数：ed_regularNewValue**

- 展示名称：剩余数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_regularNewValue
- 生成字段名：personal.ed_regularNewValue
- 说明：剩余数量
- 原始数据类型：int

**参数：ed_targetType**

- 展示名称：作用对象类型（加速的建筑组，造兵的兵种类型）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetType
- 生成字段名：personal.ed_targetType
- 说明：作用对象类型（加速的建筑组，造兵的兵种类型）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_route**

- 展示名称：变化途径（变化原因）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_route
- 生成字段名：personal.ed_route
- 说明：变化途径（变化原因）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_targetId**

- 展示名称：作用对象ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetId
- 生成字段名：personal.ed_targetId
- 说明：作用对象ID
- 原始数据类型：string
- 参数备注：根据不同途径记录不同内容<br>比如：途径是建筑升级就写建筑ID

## 事件：EnergyChange

**事件说明**

- 展示名称：体力变动
- 事件分类：资源变化
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：大本等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：大本等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_change**

- 展示名称：体力变化量
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_change
- 生成字段名：personal.ed_change
- 说明：体力变化量
- 原始数据类型：object
- 参数备注：{"oil": 10,"gold":10} 对象value为数值类型，具体见【枚举说明】
- 已知子字段映射：
  - oil：JSON路径 `$.ed_change.oil`；生成字段名 `personal.ed_change.oil`
  - gold：JSON路径 `$.ed_change.gold`；生成字段名 `personal.ed_change.gold`

**参数：ed_stock**

- 展示名称：资源存量（变化后）
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_stock
- 生成字段名：personal.ed_stock
- 说明：资源存量（变化后）
- 原始数据类型：object
- 参数备注：{"oil": 10,"gold":10} 对象value为数值类型，具体见【枚举说明】
- 已知子字段映射：
  - oil：JSON路径 `$.ed_stock.oil`；生成字段名 `personal.ed_stock.oil`
  - gold：JSON路径 `$.ed_stock.gold`；生成字段名 `personal.ed_stock.gold`

**参数：ed_targetType**

- 展示名称：作用对象类型（加速的建筑类型，造兵的兵种）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetType
- 生成字段名：personal.ed_targetType
- 说明：作用对象类型（加速的建筑类型，造兵的兵种）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_targetId**

- 展示名称：作用对象ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetId
- 生成字段名：personal.ed_targetId
- 说明：作用对象ID
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

**参数：ed_route**

- 展示名称：变化途径（变化原因）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_route
- 生成字段名：personal.ed_route
- 说明：变化途径（变化原因）
- 原始数据类型：string
- 参数备注：具体见【枚举说明】

## 事件：BuildingUpgrade

**事件说明**

- 展示名称：建筑创建/升级
- 事件分类：建筑
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_uuid**

- 展示名称：建筑uuid
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_uuid
- 生成字段名：personal.ed_uuid
- 说明：建筑uuid
- 原始数据类型：string
- 参数备注：系统生成，用于同一group不同建筑区分

**参数：ed_metaId**

- 展示名称：建筑配表id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_metaId
- 生成字段名：personal.ed_metaId
- 说明：建筑配表id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑ID

**参数：ed_buildingId**

- 展示名称：建筑group id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingId
- 生成字段名：personal.ed_buildingId
- 说明：建筑group id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑group id

**参数：ed_oldLevel**

- 展示名称：升级前建筑等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_oldLevel
- 生成字段名：personal.ed_oldLevel
- 说明：升级前建筑等级
- 原始数据类型：int
- 参数备注：升级前建筑大等级

**参数：ed_newLevel**

- 展示名称：升级后建筑等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_newLevel
- 生成字段名：personal.ed_newLevel
- 说明：升级后建筑等级
- 原始数据类型：int
- 参数备注：升级后建筑大等级，如果升级小等级，大等级不变则升级前后等级相同

## 事件：HealArmy

**事件说明**

- 展示名称：治疗弟子（游历）
- 事件分类：弟子
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：大本等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：大本等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_armyList**

- 展示名称：弟子构成
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_armyList
- 生成字段名：personal.ed_armyList
- 说明：弟子构成
- 原始数据类型：object
- 参数备注：[{"change":6,"num":110,"soldier":1102},...]
- 已知子字段映射：
  - change：JSON路径 `$.ed_armyList.change`；生成字段名 `personal.ed_armyList.change`
  - num：JSON路径 `$.ed_armyList.num`；生成字段名 `personal.ed_armyList.num`
  - soldier：JSON路径 `$.ed_armyList.soldier`；生成字段名 `personal.ed_armyList.soldier`

## 事件：ArmyUpgrade

**事件说明**

- 展示名称：弟子升阶
- 事件分类：弟子
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：大本等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：大本等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_metaId**

- 展示名称：建筑配表id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_metaId
- 生成字段名：personal.ed_metaId
- 说明：建筑配表id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑ID

**参数：ed_buildingId**

- 展示名称：建筑group id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingId
- 生成字段名：personal.ed_buildingId
- 说明：建筑group id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑group id

**参数：ed_oldArmyId**

- 展示名称：升阶前弟子id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_oldArmyId
- 生成字段名：personal.ed_oldArmyId
- 说明：升阶前弟子id
- 原始数据类型：int
- 参数备注：soldier表的弟子id

**参数：ed_newArmyId**

- 展示名称：升阶后弟子id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_newArmyId
- 生成字段名：personal.ed_newArmyId
- 说明：升阶后弟子id
- 原始数据类型：int
- 参数备注：soldier表的弟子id

**参数：ed_oldArmyLevel**

- 展示名称：升阶前弟子等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_oldArmyLevel
- 生成字段名：personal.ed_oldArmyLevel
- 说明：升阶前弟子等级
- 原始数据类型：int
- 参数备注：soldier表的level

**参数：ed_newArmyLevel**

- 展示名称：升阶后弟子等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_newArmyLevel
- 生成字段名：personal.ed_newArmyLevel
- 说明：升阶后弟子等级
- 原始数据类型：int
- 参数备注：soldier表的level

## 事件：TrainArmy

**事件说明**

- 展示名称：训练弟子
- 事件分类：弟子
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：大本等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：大本等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_metaId**

- 展示名称：建筑配表id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_metaId
- 生成字段名：personal.ed_metaId
- 说明：建筑配表id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑ID

**参数：ed_buildingId**

- 展示名称：建筑group id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingId
- 生成字段名：personal.ed_buildingId
- 说明：建筑group id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑group id

**参数：ed_countNow**

- 展示名称：当前弟子总数（增加后）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_countNow
- 生成字段名：personal.ed_countNow
- 说明：当前弟子总数（增加后）
- 原始数据类型：int

**参数：ed_countAdd**

- 展示名称：本次增加弟子数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_countAdd
- 生成字段名：personal.ed_countAdd
- 说明：本次增加弟子数量
- 原始数据类型：int

## 事件：TaskFinish

**事件说明**

- 展示名称：任务完成
- 事件分类：任务
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_taskId**

- 展示名称：任务id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskId
- 生成字段名：personal.ed_taskId
- 说明：任务id
- 原始数据类型：int
- 参数备注：对应任务类型的具体ID

**参数：ed_taskGroup**

- 展示名称：任务组
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskGroup
- 生成字段名：personal.ed_taskGroup
- 说明：任务组
- 原始数据类型：int

**参数：ed_taskType**

- 展示名称：任务类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskType
- 生成字段名：personal.ed_taskType
- 说明：任务类型
- 原始数据类型：int
- 参数备注：task表中的task_type

## 事件：TaskReward

**事件说明**

- 展示名称：任务领奖
- 事件分类：任务
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_taskId**

- 展示名称：任务id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskId
- 生成字段名：personal.ed_taskId
- 说明：任务id
- 原始数据类型：int
- 参数备注：对应任务类型的具体ID

**参数：ed_taskGroup**

- 展示名称：任务组
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskGroup
- 生成字段名：personal.ed_taskGroup
- 说明：任务组
- 原始数据类型：int

**参数：ed_taskType**

- 展示名称：任务类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_taskType
- 生成字段名：personal.ed_taskType
- 说明：任务类型
- 原始数据类型：int
- 参数备注：task表中的task_type

## 事件：HeroRecruit

**事件说明**

- 展示名称：招募（长老/古宝）
- 事件分类：抽卡
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_cardType**

- 展示名称：卡池类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cardType
- 生成字段名：personal.ed_cardType
- 说明：卡池类型
- 原始数据类型：int
- 参数备注：卡池id

**参数：ed_costType**

- 展示名称：抽卡货币类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_costType
- 生成字段名：personal.ed_costType
- 说明：抽卡货币类型
- 原始数据类型：string
- 参数备注：用抽卡券/免费<br>costItem/costFree

**参数：ed_recruitTimes**

- 展示名称：抽取次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_recruitTimes
- 生成字段名：personal.ed_recruitTimes
- 说明：抽取次数
- 原始数据类型：int
- 参数备注：1或10

**参数：ed_drawResult**

- 展示名称：抽卡结果
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_drawResult
- 生成字段名：personal.ed_drawResult
- 说明：抽卡结果
- 原始数据类型：object

## 事件：HeroStarUp

**事件说明**

- 展示名称：弟子天命等级提升
- 事件分类：长老
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：长老id
- 原始数据类型：int
- 参数备注：hero表长老id

**参数：ed_heroLevel**

- 展示名称：长老等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroLevel
- 生成字段名：personal.ed_heroLevel
- 说明：长老等级
- 原始数据类型：int

**参数：ed_oldStar**

- 展示名称：突破前的长老天命等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_oldStar
- 生成字段名：personal.ed_oldStar
- 说明：突破前的长老天命等级
- 原始数据类型：int
- 参数备注：hero表的hero_star里的star

**参数：ed_newStar**

- 展示名称：突破后的长老天命等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_newStar
- 生成字段名：personal.ed_newStar
- 说明：突破后的长老天命等级
- 原始数据类型：int
- 参数备注：hero表的hero_star里的star

## 事件：HeroLevelUp

**事件说明**

- 展示名称：长老升级
- 事件分类：长老
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：长老id
- 原始数据类型：int
- 参数备注：hero表长老id

**参数：ed_heroStar**

- 展示名称：长老当前天命等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroStar
- 生成字段名：personal.ed_heroStar
- 说明：长老当前天命等级
- 原始数据类型：int
- 参数备注：hero表的hero_star里的star

**参数：ed_oldLevel**

- 展示名称：升级前的长老等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_oldLevel
- 生成字段名：personal.ed_oldLevel
- 说明：升级前的长老等级
- 原始数据类型：int

**参数：ed_currentLevel**

- 展示名称：升级后的长老等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentLevel
- 生成字段名：personal.ed_currentLevel
- 说明：升级后的长老等级
- 原始数据类型：int

## 事件：EquipmentLevelUp

**事件说明**

- 展示名称：装备升级
- 事件分类：装备
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_equipId**

- 展示名称：装备唯一id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipId
- 生成字段名：personal.ed_equipId
- 说明：装备唯一id
- 原始数据类型：int

**参数：ed_equipItemId**

- 展示名称：装备itemId
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipItemId
- 生成字段名：personal.ed_equipItemId
- 说明：装备itemId
- 原始数据类型：int
- 参数备注：item表的装备id

**参数：ed_equipInfoOld**

- 展示名称：装备升级前属性
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipInfoOld
- 生成字段名：personal.ed_equipInfoOld
- 说明：装备升级前属性
- 原始数据类型：object
- 参数备注：例如：{"itemid":10001,"basic1id":10,"basic1num":0.221,"basic2id":10,"basic2num":0.221,"special1id":10,"special1num":0.221,"special2id":10,"special2num":0.221,"special3id":10,"special3num":0.221,"special4id":10,"special4num":0.221}<br>仅传属性，normalPro{key1:101;value:1090}{key2:102;value:1090},randomPro{key1:101;value:1090}{key2:102;value:1090}{key3:102;value:1090}{key4:102;value:1090}
- 已知子字段映射：
  - itemid：JSON路径 `$.ed_equipInfoOld.itemid`；生成字段名 `personal.ed_equipInfoOld.itemid`
  - basic1id：JSON路径 `$.ed_equipInfoOld.basic1id`；生成字段名 `personal.ed_equipInfoOld.basic1id`
  - basic1num：JSON路径 `$.ed_equipInfoOld.basic1num`；生成字段名 `personal.ed_equipInfoOld.basic1num`
  - basic2id：JSON路径 `$.ed_equipInfoOld.basic2id`；生成字段名 `personal.ed_equipInfoOld.basic2id`
  - basic2num：JSON路径 `$.ed_equipInfoOld.basic2num`；生成字段名 `personal.ed_equipInfoOld.basic2num`
  - special1id：JSON路径 `$.ed_equipInfoOld.special1id`；生成字段名 `personal.ed_equipInfoOld.special1id`
  - special1num：JSON路径 `$.ed_equipInfoOld.special1num`；生成字段名 `personal.ed_equipInfoOld.special1num`
  - special2id：JSON路径 `$.ed_equipInfoOld.special2id`；生成字段名 `personal.ed_equipInfoOld.special2id`
  - special2num：JSON路径 `$.ed_equipInfoOld.special2num`；生成字段名 `personal.ed_equipInfoOld.special2num`
  - special3id：JSON路径 `$.ed_equipInfoOld.special3id`；生成字段名 `personal.ed_equipInfoOld.special3id`
  - special3num：JSON路径 `$.ed_equipInfoOld.special3num`；生成字段名 `personal.ed_equipInfoOld.special3num`
  - special4id：JSON路径 `$.ed_equipInfoOld.special4id`；生成字段名 `personal.ed_equipInfoOld.special4id`
  - special4num：JSON路径 `$.ed_equipInfoOld.special4num`；生成字段名 `personal.ed_equipInfoOld.special4num`

**参数：ed_equipInfoNew**

- 展示名称：装备升级后属性
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipInfoNew
- 生成字段名：personal.ed_equipInfoNew
- 说明：装备升级后属性
- 原始数据类型：object
- 参数备注：仅传属性，normalPro{key1:101;value:1090}{key2:102;value:1090},randomPro{key1:101;value:1090}{key2:102;value:1090}{key3:102;value:1090}{key4:102;value:1090}

**参数：ed_equipUpgradeInfo**

- 展示名称：本次升级属性变化
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipUpgradeInfo
- 生成字段名：personal.ed_equipUpgradeInfo
- 说明：本次升级属性变化
- 原始数据类型：object
- 参数备注：例如：{"itemid":10001,"attributeid":10,"change":10}
- 已知子字段映射：
  - itemid：JSON路径 `$.ed_equipUpgradeInfo.itemid`；生成字段名 `personal.ed_equipUpgradeInfo.itemid`
  - attributeid：JSON路径 `$.ed_equipUpgradeInfo.attributeid`；生成字段名 `personal.ed_equipUpgradeInfo.attributeid`
  - change：JSON路径 `$.ed_equipUpgradeInfo.change`；生成字段名 `personal.ed_equipUpgradeInfo.change`

**参数：ed_equipOldLevel**

- 展示名称：装备升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipOldLevel
- 生成字段名：personal.ed_equipOldLevel
- 说明：装备升级前等级
- 原始数据类型：int
- 参数备注：equip表中equip_level的lv字段

**参数：ed_equipNewLevel**

- 展示名称：装备升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipNewLevel
- 生成字段名：personal.ed_equipNewLevel
- 说明：装备升级后等级
- 原始数据类型：int
- 参数备注：equip表中equip_level的lv字段

**参数：ed_equipUpgradeCost**

- 展示名称：升级消耗
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipUpgradeCost
- 生成字段名：personal.ed_equipUpgradeCost
- 说明：升级消耗
- 原始数据类型：int
- 参数备注：包含精炼石和装备 {itemId:10001;number:2};{itemId:10002;number:3}...

## 事件：EquipmentChange

**事件说明**

- 展示名称：装备更换（含卸下和一键装备）
- 事件分类：装备
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：长老id
- 原始数据类型：int
- 参数备注：hero表长老id

**参数：equipGuidOld**

- 展示名称：装备唯一id更换前
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.equipGuidOld
- 生成字段名：personal.equipGuidOld
- 说明：装备唯一id更换前
- 原始数据类型：int
- 参数备注：如果为装备位空则为 -1

**参数：equipGuidNew**

- 展示名称：装备唯一id更换后
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.equipGuidNew
- 生成字段名：personal.equipGuidNew
- 说明：装备唯一id更换后
- 原始数据类型：int

**参数：equipItemIdOld**

- 展示名称：装备itemid更换前
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.equipItemIdOld
- 生成字段名：personal.equipItemIdOld
- 说明：装备itemid更换前
- 原始数据类型：int
- 参数备注：如果为装备位空则为 -1

**参数：equipItemIdNew**

- 展示名称：装备itemid更换后
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.equipItemIdNew
- 生成字段名：personal.equipItemIdNew
- 说明：装备itemid更换后
- 原始数据类型：int

**参数：ed_effectHero**

- 展示名称：所操作英雄ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_effectHero
- 生成字段名：personal.ed_effectHero
- 说明：所操作英雄ID
- 原始数据类型：int

**参数：ed_resetAutoEquip**

- 展示名称：是否为重置英雄自动脱装
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resetAutoEquip
- 生成字段名：personal.ed_resetAutoEquip
- 说明：是否为重置英雄自动脱装
- 原始数据类型：int
- 参数备注：1为重置，2为非重置

**参数：ed_equipAllOld**

- 展示名称：装备全位置更换前
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipAllOld
- 生成字段名：personal.ed_equipAllOld
- 说明：装备全位置更换前
- 原始数据类型：object
- 参数备注：4个装备全部显示，如有装备则格式为："equipId":10001,"equipTpId":11202,"level":12,normalPro{key1:101;value:1090}{key2:102;value:1090},randomPro{key1:101;value:1090}{key2:102;value:1090}{key3:102;value:1090}{key4:102;value:1090}

**参数：ed_equipAllNew**

- 展示名称：装备全位置更换后
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipAllNew
- 生成字段名：personal.ed_equipAllNew
- 说明：装备全位置更换后
- 原始数据类型：object
- 参数备注：4个装备全部显示，如有装备则格式为："equipid":10001,"equipTpid":11202,"level":12,normalPro{key1:101;value:1090}{key2:102;value:1090},randomPro{key1:101;value:1090}{key2:102;value:1090}{key3:102;value:1090}{key4:102;value:1090}

## 事件：MarketSale

**事件说明**

- 展示名称：市集上架/更换商品
- 事件分类：市集
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_marketBuilding**

- 展示名称：市集建筑ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_marketBuilding
- 生成字段名：personal.ed_marketBuilding
- 说明：市集建筑ID
- 原始数据类型：int
- 参数备注：buildingMarket表的建筑id

**参数：ed_marketSaleOld**

- 展示名称：市集上架/更换前商品
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_marketSaleOld
- 生成字段名：personal.ed_marketSaleOld
- 说明：市集上架/更换前商品
- 原始数据类型：object
- 参数备注：例如：{"goodid":1,"goodnum":105}，如果为空则id为-1，数量为-1
- 已知子字段映射：
  - goodid：JSON路径 `$.ed_marketSaleOld.goodid`；生成字段名 `personal.ed_marketSaleOld.goodid`
  - goodnum：JSON路径 `$.ed_marketSaleOld.goodnum`；生成字段名 `personal.ed_marketSaleOld.goodnum`

**参数：ed_marketSaleNew**

- 展示名称：市集上架/更换后商品
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_marketSaleNew
- 生成字段名：personal.ed_marketSaleNew
- 说明：市集上架/更换后商品
- 原始数据类型：object
- 参数备注：例如：{"goodid":1,"goodnum":105}，如果为空则id为-1，数量为-1
- 已知子字段映射：
  - goodid：JSON路径 `$.ed_marketSaleNew.goodid`；生成字段名 `personal.ed_marketSaleNew.goodid`
  - goodnum：JSON路径 `$.ed_marketSaleNew.goodnum`；生成字段名 `personal.ed_marketSaleNew.goodnum`

## 事件：BuildingHeroWork

**事件说明**

- 展示名称：长老上任（资源建筑/市集建筑）
- 事件分类：建筑
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_uuid**

- 展示名称：建筑uuid
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_uuid
- 生成字段名：personal.ed_uuid
- 说明：建筑uuid
- 原始数据类型：string
- 参数备注：系统生成，用于同一group不同建筑区分

**参数：ed_metaId**

- 展示名称：建筑配表id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_metaId
- 生成字段名：personal.ed_metaId
- 说明：建筑配表id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑ID

**参数：ed_buildingId**

- 展示名称：建筑group id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingId
- 生成字段名：personal.ed_buildingId
- 说明：建筑group id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑group id

**参数：ed_heroSwitchType**

- 展示名称：上任类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroSwitchType
- 生成字段名：personal.ed_heroSwitchType
- 说明：上任类型
- 原始数据类型：int
- 参数备注：1001为资源建筑，1005为市集建筑

**参数：ed_heroSwitchOld**

- 展示名称：上任前长老配置
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroSwitchOld
- 生成字段名：personal.ed_heroSwitchOld
- 说明：上任前长老配置
- 原始数据类型：object
- 参数备注：例如：{10001,...}，如果为空则heroid为0，如果位置未解锁则t为-1

**参数：ed_heroSwitchNew**

- 展示名称：上任后长老配置
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroSwitchNew
- 生成字段名：personal.ed_heroSwitchNew
- 说明：上任后长老配置
- 原始数据类型：object
- 参数备注：例如：{10001,...}，如果为空则heroid为0，如果位置未解锁则t为-1

## 事件：BuildingImprove

**事件说明**

- 展示名称：资源建筑提升
- 事件分类：建筑
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_uuid**

- 展示名称：建筑uuid
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_uuid
- 生成字段名：personal.ed_uuid
- 说明：建筑uuid
- 原始数据类型：string
- 参数备注：系统生成，用于同一group不同建筑区分

**参数：ed_metaId**

- 展示名称：建筑配表id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_metaId
- 生成字段名：personal.ed_metaId
- 说明：建筑配表id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑ID

**参数：ed_buildingId**

- 展示名称：建筑group id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingId
- 生成字段名：personal.ed_buildingId
- 说明：建筑group id
- 原始数据类型：int
- 参数备注：buildingResUpgrade表中的建筑group id

**参数：ed_buildingSubId**

- 展示名称：建筑升级子项目id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_buildingSubId
- 生成字段名：personal.ed_buildingSubId
- 说明：建筑升级子项目id
- 原始数据类型：int
- 参数备注：building表的buildingSub中的id

**参数：ed_subOldLevel**

- 展示名称：升级前子项目等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_subOldLevel
- 生成字段名：personal.ed_subOldLevel
- 说明：升级前子项目等级
- 原始数据类型：int
- 参数备注：升级前子项目等级

**参数：ed_subNewLevel**

- 展示名称：升级后子项目等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_subNewLevel
- 生成字段名：personal.ed_subNewLevel
- 说明：升级后子项目等级
- 原始数据类型：int
- 参数备注：升级后子项目等级

## 事件：TowerClimbChallenge

**事件说明**

- 展示名称：锁妖塔挑战
- 事件分类：锁妖塔
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_towerNum**

- 展示名称：锁妖塔挑战前层数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_towerNum
- 生成字段名：personal.ed_towerNum
- 说明：锁妖塔挑战前层数
- 原始数据类型：int
- 参数备注：climbingTower的id

**参数：ed_battleId**

- 展示名称：本次战斗唯一id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleId
- 生成字段名：personal.ed_battleId
- 说明：本次战斗唯一id
- 原始数据类型：int
- 参数备注：本场战斗唯一id

**参数：ed_battleTeam**

- 展示名称：战斗阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleTeam
- 生成字段名：personal.ed_battleTeam
- 说明：战斗阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_battleTeam[0].heroid`；生成字段名 `personal.ed_battleTeam[0].heroid`
  - [0].seat：JSON路径 `$.ed_battleTeam[0].seat`；生成字段名 `personal.ed_battleTeam[0].seat`
  - [0].level：JSON路径 `$.ed_battleTeam[0].level`；生成字段名 `personal.ed_battleTeam[0].level`
  - [0].star：JSON路径 `$.ed_battleTeam[0].star`；生成字段名 `personal.ed_battleTeam[0].star`

**参数：ed_towerResult**

- 展示名称：锁妖塔挑战结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_towerResult
- 生成字段名：personal.ed_towerResult
- 说明：锁妖塔挑战结果
- 原始数据类型：int
- 参数备注：根据挑战者结果，win/lose

## 事件：ArenaBattleStart

**事件说明**

- 展示名称：斗法台挑战开始
- 事件分类：斗法台
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_traceId**

- 展示名称：traceId
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_traceId
- 生成字段名：personal.ed_traceId
- 说明：traceId
- 原始数据类型：int

**参数：ed_battleTeamAttack**

- 展示名称：挑战者战斗阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleTeamAttack
- 生成字段名：personal.ed_battleTeamAttack
- 说明：挑战者战斗阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_battleTeamAttack[0].heroid`；生成字段名 `personal.ed_battleTeamAttack[0].heroid`
  - [0].seat：JSON路径 `$.ed_battleTeamAttack[0].seat`；生成字段名 `personal.ed_battleTeamAttack[0].seat`
  - [0].level：JSON路径 `$.ed_battleTeamAttack[0].level`；生成字段名 `personal.ed_battleTeamAttack[0].level`
  - [0].star：JSON路径 `$.ed_battleTeamAttack[0].star`；生成字段名 `personal.ed_battleTeamAttack[0].star`

**参数：ed_battleTeamDefence**

- 展示名称：被挑战者战斗阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleTeamDefence
- 生成字段名：personal.ed_battleTeamDefence
- 说明：被挑战者战斗阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_battleTeamDefence[0].heroid`；生成字段名 `personal.ed_battleTeamDefence[0].heroid`
  - [0].seat：JSON路径 `$.ed_battleTeamDefence[0].seat`；生成字段名 `personal.ed_battleTeamDefence[0].seat`
  - [0].level：JSON路径 `$.ed_battleTeamDefence[0].level`；生成字段名 `personal.ed_battleTeamDefence[0].level`
  - [0].star：JSON路径 `$.ed_battleTeamDefence[0].star`；生成字段名 `personal.ed_battleTeamDefence[0].star`

**参数：ed_arenaOverPower**

- 展示名称：斗法台碾压战斗
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_arenaOverPower
- 生成字段名：personal.ed_arenaOverPower
- 说明：斗法台碾压战斗
- 原始数据类型：int
- 参数备注：大于0代表碾压次数，0代表非碾压战斗

**参数：ed_npc**

- 展示名称：对战目标是否NPC
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_npc
- 生成字段名：personal.ed_npc
- 说明：对战目标是否NPC
- 原始数据类型：bool

## 事件：ArenaBattleResult

**事件说明**

- 展示名称：斗法台挑战结束
- 事件分类：斗法台
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_battleId**

- 展示名称：本次战斗唯一id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleId
- 生成字段名：personal.ed_battleId
- 说明：本次战斗唯一id
- 原始数据类型：int
- 参数备注：本场战斗唯一id

**参数：ed_arenaRankOld**

- 展示名称：本次挑战前名次
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_arenaRankOld
- 生成字段名：personal.ed_arenaRankOld
- 说明：本次挑战前名次
- 原始数据类型：int
- 参数备注：名次

**参数：ed_arenaRankchange**

- 展示名称：挑战者名次变化
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_arenaRankchange
- 生成字段名：personal.ed_arenaRankchange
- 说明：挑战者名次变化
- 原始数据类型：int
- 参数备注：挑战前-挑战后的名次差值，0代表不变

**参数：ed_traceId**

- 展示名称：traceId
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_traceId
- 生成字段名：personal.ed_traceId
- 说明：traceId
- 原始数据类型：int

**参数：ed_arenaResult**

- 展示名称：斗法台挑战结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_arenaResult
- 生成字段名：personal.ed_arenaResult
- 说明：斗法台挑战结果
- 原始数据类型：int
- 参数备注：根据挑战者结果，win/lose

## 事件：ScienceStudy

**事件说明**

- 展示名称：道藏研究
- 事件分类：道藏
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_scienceId**

- 展示名称：道藏ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_scienceId
- 生成字段名：personal.ed_scienceId
- 说明：道藏ID
- 原始数据类型：int

**参数：ed_start**

- 展示名称：是否开始研究
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_start
- 生成字段名：personal.ed_start
- 说明：是否开始研究
- 原始数据类型：bool

## 事件：AutoClickResource

**事件说明**

- 展示名称：开启自动采集
- 事件分类：自动采集
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

## 事件：TeamChange

**事件说明**

- 展示名称：储存布阵信息
- 事件分类：布阵
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_teamNum**

- 展示名称：阵容id（储存位）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamNum
- 生成字段名：personal.ed_teamNum
- 说明：阵容id（储存位）
- 原始数据类型：int

**参数：ed_xianzhouId**

- 展示名称：所用仙舟ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouId
- 生成字段名：personal.ed_xianzhouId
- 说明：所用仙舟ID
- 原始数据类型：int

**参数：ed_teamInfo**

- 展示名称：储存后阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfo
- 生成字段名：personal.ed_teamInfo
- 说明：储存后阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfo[0].heroid`；生成字段名 `personal.ed_teamInfo[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfo[0].seat`；生成字段名 `personal.ed_teamInfo[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfo[0].level`；生成字段名 `personal.ed_teamInfo[0].level`
  - [0].star：JSON路径 `$.ed_teamInfo[0].star`；生成字段名 `personal.ed_teamInfo[0].star`

**参数：ed_teamType**

- 展示名称：阵容类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamType
- 生成字段名：personal.ed_teamType
- 说明：阵容类型
- 原始数据类型：int
- 参数备注：1为常规布阵，2为斗法台布阵，3为世界布阵

## 事件：Adventure

**事件说明**

- 展示名称：山海游历
- 事件分类：游历
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_adventureMap**

- 展示名称：游历地图id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureMap
- 生成字段名：personal.ed_adventureMap
- 说明：游历地图id
- 原始数据类型：int

**参数：ed_adventureId**

- 展示名称：游历关卡id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureId
- 生成字段名：personal.ed_adventureId
- 说明：游历关卡id
- 原始数据类型：int

**参数：ed_adventureHero**

- 展示名称：本次游历阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureHero
- 生成字段名：personal.ed_adventureHero
- 说明：本次游历阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_adventureHero[0].heroid`；生成字段名 `personal.ed_adventureHero[0].heroid`
  - [0].seat：JSON路径 `$.ed_adventureHero[0].seat`；生成字段名 `personal.ed_adventureHero[0].seat`
  - [0].level：JSON路径 `$.ed_adventureHero[0].level`；生成字段名 `personal.ed_adventureHero[0].level`
  - [0].star：JSON路径 `$.ed_adventureHero[0].star`；生成字段名 `personal.ed_adventureHero[0].star`

**参数：ed_adventureArmy**

- 展示名称：本次游历弟子数量变化
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureArmy
- 生成字段名：personal.ed_adventureArmy
- 说明：本次游历弟子数量变化
- 原始数据类型：object
- 参数备注：弟子1id;剩余数量;变化数量1|弟子2id;剩余数量;变化数量2……<br>[{"soldier":"1002","num":"500","change":-10},{"soldier":"1003","num":"500","change":-100},{……}]
- 已知子字段映射：
  - soldier：JSON路径 `$.ed_adventureArmy.soldier`；生成字段名 `personal.ed_adventureArmy.soldier`
  - num：JSON路径 `$.ed_adventureArmy.num`；生成字段名 `personal.ed_adventureArmy.num`
  - change：JSON路径 `$.ed_adventureArmy.change`；生成字段名 `personal.ed_adventureArmy.change`

**参数：ed_adventureBoss**

- 展示名称：boss关id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureBoss
- 生成字段名：personal.ed_adventureBoss
- 说明：boss关id
- 原始数据类型：int
- 参数备注：如果本次游历非boss关，则为 -1

## 事件：AdventureBox

**事件说明**

- 展示名称：打开游历宝箱
- 事件分类：游历
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_boxType**

- 展示名称：宝箱品质
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_boxType
- 生成字段名：personal.ed_boxType
- 说明：宝箱品质
- 原始数据类型：int

**参数：ed_boxNum**

- 展示名称：本次开启宝箱数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_boxNum
- 生成字段名：personal.ed_boxNum
- 说明：本次开启宝箱数量
- 原始数据类型：int

**参数：ed_boxInfo**

- 展示名称：宝箱id
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_boxInfo
- 生成字段名：personal.ed_boxInfo
- 说明：宝箱id
- 原始数据类型：object
- 参数备注：[{"boxNum":10,"boxId":100107}]
- 已知子字段映射：
  - [0].boxNum：JSON路径 `$.ed_boxInfo[0].boxNum`；生成字段名 `personal.ed_boxInfo[0].boxNum`
  - [0].boxId：JSON路径 `$.ed_boxInfo[0].boxId`；生成字段名 `personal.ed_boxInfo[0].boxId`

**参数：ed_boxPoint**

- 展示名称：开启后宝箱进度积分
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_boxPoint
- 生成字段名：personal.ed_boxPoint
- 说明：开启后宝箱进度积分
- 原始数据类型：int
- 参数备注：总积分

## 事件：AdventureBattle

**事件说明**

- 展示名称：游历战斗
- 事件分类：游历
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_adventureMap**

- 展示名称：游历地图id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureMap
- 生成字段名：personal.ed_adventureMap
- 说明：游历地图id
- 原始数据类型：int

**参数：ed_adventureId**

- 展示名称：游历关卡id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureId
- 生成字段名：personal.ed_adventureId
- 说明：游历关卡id
- 原始数据类型：int

**参数：ed_adventureHero**

- 展示名称：本次游历阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureHero
- 生成字段名：personal.ed_adventureHero
- 说明：本次游历阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_adventureHero[0].heroid`；生成字段名 `personal.ed_adventureHero[0].heroid`
  - [0].seat：JSON路径 `$.ed_adventureHero[0].seat`；生成字段名 `personal.ed_adventureHero[0].seat`
  - [0].level：JSON路径 `$.ed_adventureHero[0].level`；生成字段名 `personal.ed_adventureHero[0].level`
  - [0].star：JSON路径 `$.ed_adventureHero[0].star`；生成字段名 `personal.ed_adventureHero[0].star`

**参数：ed_adventureBoss**

- 展示名称：boss关id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_adventureBoss
- 生成字段名：personal.ed_adventureBoss
- 说明：boss关id
- 原始数据类型：int
- 参数备注：如果本次游历非boss关，则为 -1

**参数：ed_battleResult**

- 展示名称：游历战斗结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleResult
- 生成字段名：personal.ed_battleResult
- 说明：游历战斗结果
- 原始数据类型：int
- 参数备注：根据挑战者结果，win/lose

## 事件：mainBuildingRealmUp

**事件说明**

- 展示名称：宗门境界提升
- 事件分类：宗门境界
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_realmLevel**

- 展示名称：境界等级id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_realmLevel
- 生成字段名：personal.ed_realmLevel
- 说明：境界等级id
- 原始数据类型：int
- 参数备注：提升后的境界等级

## 事件：mainBuildingUp

**事件说明**

- 展示名称：宗门等级提升
- 事件分类：宗门等级
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20 ， 提升后的宗门等级

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

## 事件：CreateAlliance

**事件说明**

- 展示名称：创建仙盟
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_allianceFlag**

- 展示名称：仙盟旗帜
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceFlag
- 生成字段名：personal.ed_allianceFlag
- 说明：仙盟旗帜
- 原始数据类型：string

## 事件：DismissAlliance

**事件说明**

- 展示名称：解散仙盟
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

## 事件：ApplyAlliance

**事件说明**

- 展示名称：申请仙盟
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

## 事件：JoinAlliance

**事件说明**

- 展示名称：加入仙盟
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string
- 参数备注：没有盟主为负数 例如-9500005

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_getInWay**

- 展示名称：加入仙盟途径
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_getInWay
- 生成字段名：personal.ed_getInWay
- 说明：加入仙盟途径
- 原始数据类型：string
- 参数备注：create (创建加入) /apply（自由加入） /<br> approve（审批加入）/invite(邀请加入) / 自动加入

## 事件：ChangeAlliance

**事件说明**

- 展示名称：更换仙盟
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId_old**

- 展示名称：原仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId_old
- 生成字段名：personal.ed_allianceId_old
- 说明：原仙盟id
- 原始数据类型：string

**参数：ed_allianceId_new**

- 展示名称：新仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId_new
- 生成字段名：personal.ed_allianceId_new
- 说明：新仙盟id
- 原始数据类型：string

**参数：ed_allianceLevel_old**

- 展示名称：原仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel_old
- 生成字段名：personal.ed_allianceLevel_old
- 说明：原仙盟等级
- 原始数据类型：int

**参数：ed_allianceLevel_new**

- 展示名称：新仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel_new
- 生成字段名：personal.ed_allianceLevel_new
- 说明：新仙盟等级
- 原始数据类型：int

**参数：ed_currentMemberNumber_old**

- 展示名称：原仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber_old
- 生成字段名：personal.ed_currentMemberNumber_old
- 说明：原仙盟当前人数
- 原始数据类型：int

**参数：ed_currentMemberNumber_new**

- 展示名称：新仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber_new
- 生成字段名：personal.ed_currentMemberNumber_new
- 说明：新仙盟当前人数
- 原始数据类型：int

## 事件：AllianceMasterChallange

**事件说明**

- 展示名称：挑战联盟高级职位结果
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_challengeTargetPosition**

- 展示名称：挑战目标职位
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_challengeTargetPosition
- 生成字段名：personal.ed_challengeTargetPosition
- 说明：挑战目标职位
- 原始数据类型：string
- 参数备注：1盟主 0 副盟主

**参数：ed_chalengeTargetId**

- 展示名称：挑战目标id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_chalengeTargetId
- 生成字段名：personal.ed_chalengeTargetId
- 说明：挑战目标id
- 原始数据类型：string
- 参数备注：挑战的是玩家就传uid，挑战的是npc传npcid

**参数：ed_allianceChallangeResult**

- 展示名称：挑战结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceChallangeResult
- 生成字段名：personal.ed_allianceChallangeResult
- 说明：挑战结果
- 原始数据类型：int
- 参数备注：1胜利 0失败

**参数：ed_allianceChallangeAttackTeam**

- 展示名称：进攻方阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceChallangeAttackTeam
- 生成字段名：personal.ed_allianceChallangeAttackTeam
- 说明：进攻方阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55},{"heroid":10002,"seat":2,"level":55},{"heroid":10003,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_allianceChallangeAttackTeam[0].heroid`；生成字段名 `personal.ed_allianceChallangeAttackTeam[0].heroid`
  - [0].seat：JSON路径 `$.ed_allianceChallangeAttackTeam[0].seat`；生成字段名 `personal.ed_allianceChallangeAttackTeam[0].seat`
  - [0].level：JSON路径 `$.ed_allianceChallangeAttackTeam[0].level`；生成字段名 `personal.ed_allianceChallangeAttackTeam[0].level`

**参数：ed_allianceChallangeDefenceTeam**

- 展示名称：防守方阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceChallangeDefenceTeam
- 生成字段名：personal.ed_allianceChallangeDefenceTeam
- 说明：防守方阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55},{"heroid":10002,"seat":2,"level":55},{"heroid":10003,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_allianceChallangeDefenceTeam[0].heroid`；生成字段名 `personal.ed_allianceChallangeDefenceTeam[0].heroid`
  - [0].seat：JSON路径 `$.ed_allianceChallangeDefenceTeam[0].seat`；生成字段名 `personal.ed_allianceChallangeDefenceTeam[0].seat`
  - [0].level：JSON路径 `$.ed_allianceChallangeDefenceTeam[0].level`；生成字段名 `personal.ed_allianceChallangeDefenceTeam[0].level`

## 事件：AllianceJobChange

**事件说明**

- 展示名称：仙盟官职变更
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceJobOld**

- 展示名称：原职位
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJobOld
- 生成字段名：personal.ed_allianceJobOld
- 说明：原职位
- 原始数据类型：string
- 参数备注：职位对应R1~R5

**参数：ed_allianceJobNew**

- 展示名称：新职位
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJobNew
- 生成字段名：personal.ed_allianceJobNew
- 说明：新职位
- 原始数据类型：string
- 参数备注：职位对应R1~R5

**参数：ed_allianceJobNewPlayerid**

- 展示名称：新职位玩家id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJobNewPlayerid
- 生成字段名：personal.ed_allianceJobNewPlayerid
- 说明：新职位玩家id
- 原始数据类型：string

## 事件：AllianceScienceUpgrade

**事件说明**

- 展示名称：仙盟科技升级
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceName**

- 展示名称：仙盟名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceName
- 生成字段名：personal.ed_allianceName
- 说明：仙盟名称
- 原始数据类型：string

**参数：ed_allianceScienceAllLevel**

- 展示名称：总科技等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceScienceAllLevel
- 生成字段名：personal.ed_allianceScienceAllLevel
- 说明：总科技等级
- 原始数据类型：int
- 参数备注：升级后总等级

**参数：ed_allianceScienceLevelOld**

- 展示名称：升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceScienceLevelOld
- 生成字段名：personal.ed_allianceScienceLevelOld
- 说明：升级前等级
- 原始数据类型：int

**参数：ed_allianceScienceLevelNew**

- 展示名称：升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceScienceLevelNew
- 生成字段名：personal.ed_allianceScienceLevelNew
- 说明：升级后等级
- 原始数据类型：int

**参数：ed_allianceScienceId**

- 展示名称：科技id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceScienceId
- 生成字段名：personal.ed_allianceScienceId
- 说明：科技id
- 原始数据类型：int

**参数：ed_allianceScienceCost**

- 展示名称：升级消耗
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceScienceCost
- 生成字段名：personal.ed_allianceScienceCost
- 说明：升级消耗
- 原始数据类型：object
- 参数备注：{"资源1id": 10,"资源2id":10}
- 已知子字段映射：
  - ["资源1id"]：JSON路径 `$.ed_allianceScienceCost["资源1id"]`；生成字段名 `personal.ed_allianceScienceCost["资源1id"]`
  - ["资源2id"]：JSON路径 `$.ed_allianceScienceCost["资源2id"]`；生成字段名 `personal.ed_allianceScienceCost["资源2id"]`

**参数：ed_seasonId**

- 展示名称：赛季id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_seasonId
- 生成字段名：personal.ed_seasonId
- 说明：赛季id
- 原始数据类型：int

## 事件：ChangeAllianceInfo

**事件说明**

- 展示名称：修改仙盟公告
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceInfoOld**

- 展示名称：仙盟公告旧
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceInfoOld
- 生成字段名：personal.ed_allianceInfoOld
- 说明：仙盟公告旧
- 原始数据类型：string

**参数：ed_allianceInfoNew**

- 展示名称：仙盟公告新
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceInfoNew
- 生成字段名：personal.ed_allianceInfoNew
- 说明：仙盟公告新
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

## 事件：ChangeAllianceFlag

**事件说明**

- 展示名称：修改旗帜
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceFlagOld**

- 展示名称：仙盟旗帜旧
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceFlagOld
- 生成字段名：personal.ed_allianceFlagOld
- 说明：仙盟旗帜旧
- 原始数据类型：string

**参数：ed_allianceFlagNew**

- 展示名称：仙盟旗帜新
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceFlagNew
- 生成字段名：personal.ed_allianceFlagNew
- 说明：仙盟旗帜新
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

## 事件：ChangeAllianceName

**事件说明**

- 展示名称：修改仙盟名称
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceNameOld**

- 展示名称：仙盟名称旧
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceNameOld
- 生成字段名：personal.ed_allianceNameOld
- 说明：仙盟名称旧
- 原始数据类型：string

**参数：ed_allianceNameNew**

- 展示名称：仙盟名称新
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceNameNew
- 生成字段名：personal.ed_allianceNameNew
- 说明：仙盟名称新
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_currentMemberNumber**

- 展示名称：仙盟当前人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_currentMemberNumber
- 生成字段名：personal.ed_currentMemberNumber
- 说明：仙盟当前人数
- 原始数据类型：int

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

## 事件：AllianceBargaining

**事件说明**

- 展示名称：仙盟砍价
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_bargainingNumber**

- 展示名称：砍价金额
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bargainingNumber
- 生成字段名：personal.ed_bargainingNumber
- 说明：砍价金额
- 原始数据类型：int

**参数：ed_bargainingresult**

- 展示名称：砍价后结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bargainingresult
- 生成字段名：personal.ed_bargainingresult
- 说明：砍价后结果
- 原始数据类型：int

**参数：ed_payedPeople**

- 展示名称：今日礼包已购买人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_payedPeople
- 生成字段名：personal.ed_payedPeople
- 说明：今日礼包已购买人数
- 原始数据类型：int

## 事件：AllianceHelpAsk

**事件说明**

- 展示名称：请求仙盟援助
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_route**

- 展示名称：所在功能
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_route
- 生成字段名：personal.ed_route
- 说明：所在功能
- 原始数据类型：string
- 参数备注：具体见【枚举说明】，当前版本仅有道藏

## 事件：AllianceHelp

**事件说明**

- 展示名称：响应仙盟援助
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_allianceHelpAskerId**

- 展示名称：求助人id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceHelpAskerId
- 生成字段名：personal.ed_allianceHelpAskerId
- 说明：求助人id
- 原始数据类型：string

## 事件：AllianceDonate

**事件说明**

- 展示名称：仙盟捐献
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int
- 参数备注：捐献前等级

**参数：ed_donateWay**

- 展示名称：捐献方式
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_donateWay
- 生成字段名：personal.ed_donateWay
- 说明：捐献方式
- 原始数据类型：int
- 参数备注：free（免费） / pay（仙玉）/advertise（广告）

**参数：ed_relateId**

- 展示名称：关联ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_relateId
- 生成字段名：personal.ed_relateId
- 说明：关联ID
- 原始数据类型：string
- 参数备注：用于聚合AllianceDonateExp

## 事件：AllianceDonateExp

**事件说明**

- 展示名称：仙盟捐献经验变化
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceExpOld**

- 展示名称：仙盟经验旧
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceExpOld
- 生成字段名：personal.ed_allianceExpOld
- 说明：仙盟经验旧
- 原始数据类型：int
- 参数备注：捐献前的仙盟经验

**参数：ed_allianceExpNew**

- 展示名称：仙盟经验新
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceExpNew
- 生成字段名：personal.ed_allianceExpNew
- 说明：仙盟经验新
- 原始数据类型：int
- 参数备注：捐献后的仙盟经验

**参数：ed_allianceLevelOld**

- 展示名称：仙盟等级旧
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevelOld
- 生成字段名：personal.ed_allianceLevelOld
- 说明：仙盟等级旧
- 原始数据类型：int
- 参数备注：捐献前的仙盟等级

**参数：ed_allianceLevelNew**

- 展示名称：仙盟等级新
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevelNew
- 生成字段名：personal.ed_allianceLevelNew
- 说明：仙盟等级新
- 原始数据类型：int
- 参数备注：捐献后的仙盟等级

## 事件：AllianceApproval

**事件说明**

- 展示名称：仙盟审批
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_ApprovalTarget**

- 展示名称：审批对象
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ApprovalTarget
- 生成字段名：personal.ed_ApprovalTarget
- 说明：审批对象
- 原始数据类型：string
- 参数备注：用户id，支持多用户的数组

**参数：ed_ApprovalResult**

- 展示名称：审批结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ApprovalResult
- 生成字段名：personal.ed_ApprovalResult
- 说明：审批结果
- 原始数据类型：int
- 参数备注：approve（通过）/refuse（拒绝）/refuseAll（一键拒绝）

## 事件：AllianceBossSacrifice

**事件说明**

- 展示名称：仙盟BOSS祭祀
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_sacrificeType**

- 展示名称：祭祀类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sacrificeType
- 生成字段名：personal.ed_sacrificeType
- 说明：祭祀类型
- 原始数据类型：int
- 参数备注：1（仙玉）/2（非仙玉）

**参数：ed_bossAddLevel**

- 展示名称：祭祀加成等级对应ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossAddLevel
- 生成字段名：personal.ed_bossAddLevel
- 说明：祭祀加成等级对应ID
- 原始数据类型：int
- 参数备注：祭祀后的结果等级的技能ID

## 事件：AllianceBossBattle

**事件说明**

- 展示名称：仙盟BOSS战斗
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_bossHeroInfo**

- 展示名称：战斗阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossHeroInfo
- 生成字段名：personal.ed_bossHeroInfo
- 说明：战斗阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_bossHeroInfo[0].heroid`；生成字段名 `personal.ed_bossHeroInfo[0].heroid`
  - [0].seat：JSON路径 `$.ed_bossHeroInfo[0].seat`；生成字段名 `personal.ed_bossHeroInfo[0].seat`
  - [0].level：JSON路径 `$.ed_bossHeroInfo[0].level`；生成字段名 `personal.ed_bossHeroInfo[0].level`
  - [0].star：JSON路径 `$.ed_bossHeroInfo[0].star`；生成字段名 `personal.ed_bossHeroInfo[0].star`

**参数：ed_bossBattleResult**

- 展示名称：战斗结果
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossBattleResult
- 生成字段名：personal.ed_bossBattleResult
- 说明：战斗结果
- 原始数据类型：string
- 参数备注：本次造成的总伤害值

**参数：ed_bossBattleTimes**

- 展示名称：战斗次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossBattleTimes
- 生成字段名：personal.ed_bossBattleTimes
- 说明：战斗次数
- 原始数据类型：int
- 参数备注：本次打点为当日第几次战斗，最多5

## 事件：AllianceBossSale

**事件说明**

- 展示名称：仙盟BOSS拍卖
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int

**参数：ed_bossSaleType**

- 展示名称：竞拍类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossSaleType
- 生成字段名：personal.ed_bossSaleType
- 说明：竞拍类型
- 原始数据类型：int
- 参数备注：1（一口价）/0（竞拍）

**参数：ed_bossSaleNum**

- 展示名称：竞拍价格
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossSaleNum
- 生成字段名：personal.ed_bossSaleNum
- 说明：竞拍价格
- 原始数据类型：int

**参数：ed_bossSaleArea**

- 展示名称：竞拍区域
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_bossSaleArea
- 生成字段名：personal.ed_bossSaleArea
- 说明：竞拍区域
- 原始数据类型：int
- 参数备注：1（仙盟拍卖）/2（全服拍卖）

## 事件：CreatePlayer

**事件说明**

- 展示名称：角色创建
- 事件分类：角色
- 事件来源：后端
- 优先级：必打点

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_sexType**

- 展示名称：性别选择
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sexType
- 生成字段名：personal.ed_sexType
- 说明：性别选择
- 原始数据类型：int
- 参数备注：1为女，2为男

**参数：ed_playerName**

- 展示名称：玩家名称
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_playerName
- 生成字段名：personal.ed_playerName
- 说明：玩家名称
- 原始数据类型：string
- 参数备注：系统随机生成的

**参数：ed_serverPlayerNumber**

- 展示名称：服务器人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverPlayerNumber
- 生成字段名：personal.ed_serverPlayerNumber
- 说明：服务器人数
- 原始数据类型：int
- 参数备注：包含当前这个角色创建（也包含未确认性别就离开的玩家）

## 事件：ChangePlayerName

**事件说明**

- 展示名称：角色改名
- 事件分类：角色
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_changeNameType**

- 展示名称：修改方式
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_changeNameType
- 生成字段名：personal.ed_changeNameType
- 说明：修改方式
- 原始数据类型：int
- 参数备注：1为免费修改，2为付费修改

**参数：ed_playerNameOld**

- 展示名称：玩家名称旧
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_playerNameOld
- 生成字段名：personal.ed_playerNameOld
- 说明：玩家名称旧
- 原始数据类型：string

**参数：ed_playerNameNew**

- 展示名称：玩家名称新
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_playerNameNew
- 生成字段名：personal.ed_playerNameNew
- 说明：玩家名称新
- 原始数据类型：string

## 事件：HeroReset

**事件说明**

- 展示名称：长老重置
- 事件分类：长老
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：长老id
- 原始数据类型：int
- 参数备注：hero表长老id

**参数：ed_heroLevel**

- 展示名称：长老等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroLevel
- 生成字段名：personal.ed_heroLevel
- 说明：长老等级
- 原始数据类型：int
- 参数备注：长老重置前等级

**参数：ed_heroStar**

- 展示名称：长老天命
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroStar
- 生成字段名：personal.ed_heroStar
- 说明：长老天命
- 原始数据类型：int
- 参数备注：长老重置前天命

## 事件：EquipmentDelete

**事件说明**

- 展示名称：装备删除（熔炼）
- 事件分类：装备
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_equipDelete**

- 展示名称：删除装备
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipDelete
- 生成字段名：personal.ed_equipDelete
- 说明：删除装备
- 原始数据类型：object
- 参数备注：装备唯一id和itemid

**参数：ed_equipDeleteBackItem**

- 展示名称：删除装备返还
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_equipDeleteBackItem
- 生成字段名：personal.ed_equipDeleteBackItem
- 说明：删除装备返还
- 原始数据类型：object
- 参数备注：道具id和数量， {itemId:10001;number:2};{itemId:10002;number:3}...

## 事件：HeroStarGift

**事件说明**

- 展示名称：领取天命馈赠
- 事件分类：弟子
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：大本等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：大本等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_heroId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_heroId
- 生成字段名：personal.ed_heroId
- 说明：长老id
- 原始数据类型：int
- 参数备注：hero表长老id

**参数：ed_starExp**

- 展示名称：天命经验数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_starExp
- 生成字段名：personal.ed_starExp
- 说明：天命经验数量
- 原始数据类型：int

**参数：ed_ifStarGiftUpgrade**

- 展示名称：本次是否升级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ifStarGiftUpgrade
- 生成字段名：personal.ed_ifStarGiftUpgrade
- 说明：本次是否升级
- 原始数据类型：int
- 参数备注：1升级，0未升级

**参数：ed_giftOldLevel**

- 展示名称：领取前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_giftOldLevel
- 生成字段名：personal.ed_giftOldLevel
- 说明：领取前等级
- 原始数据类型：int

**参数：ed_giftNewLevel**

- 展示名称：领取后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_giftNewLevel
- 生成字段名：personal.ed_giftNewLevel
- 说明：领取后等级
- 原始数据类型：int

## 事件：PetLevelUp

**事件说明**

- 展示名称：灵兽升级
- 事件分类：灵兽
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petId**

- 展示名称：灵兽id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petId
- 生成字段名：personal.ed_petId
- 说明：灵兽id
- 原始数据类型：int
- 参数备注：灵兽id

**参数：ed_petoldLevel**

- 展示名称：升级前的灵兽等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petoldLevel
- 生成字段名：personal.ed_petoldLevel
- 说明：升级前的灵兽等级
- 原始数据类型：int

**参数：ed_petcurrentLevel**

- 展示名称：升级后的灵兽等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petcurrentLevel
- 生成字段名：personal.ed_petcurrentLevel
- 说明：升级后的灵兽等级
- 原始数据类型：int

## 事件：PetDrawCard

**事件说明**

- 展示名称：灵兽孵蛋（抽卡）
- 事件分类：灵兽
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petCardType**

- 展示名称：卡池类型
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petCardType
- 生成字段名：personal.ed_petCardType
- 说明：卡池类型
- 原始数据类型：object
- 参数备注：卡池id组合（spiritualPetIncubate里的id），可能跨度多个卡池<br>例：{Id:10001;num:2};{Id:10002;num:2}

**参数：ed_petRecruitTimes**

- 展示名称：孵化次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petRecruitTimes
- 生成字段名：personal.ed_petRecruitTimes
- 说明：孵化次数
- 原始数据类型：int
- 参数备注：对应次数，最多为50，

**参数：ed_petDrawResult**

- 展示名称：孵化结果
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petDrawResult
- 生成字段名：personal.ed_petDrawResult
- 说明：孵化结果
- 原始数据类型：object
- 参数备注：用json格式对象组记录物品id和数量即可， [{"itemid":"10001","num":10},{"itemid":"10002","num":10}]
- 已知子字段映射：
  - [0].itemid：JSON路径 `$.ed_petDrawResult[0].itemid`；生成字段名 `personal.ed_petDrawResult[0].itemid`
  - [0].num：JSON路径 `$.ed_petDrawResult[0].num`；生成字段名 `personal.ed_petDrawResult[0].num`

## 事件：PetTeamChange

**事件说明**

- 展示名称：储存灵兽乱斗阵容信息
- 事件分类：灵兽
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petTeamInfo**

- 展示名称：储存后灵兽阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petTeamInfo
- 生成字段名：personal.ed_petTeamInfo
- 说明：储存后灵兽阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"petid":10001,"seat":1,"level":55},{"petid":10002,"seat":2,"level":55},{"petid":10003,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].petid：JSON路径 `$.ed_petTeamInfo[0].petid`；生成字段名 `personal.ed_petTeamInfo[0].petid`
  - [0].seat：JSON路径 `$.ed_petTeamInfo[0].seat`；生成字段名 `personal.ed_petTeamInfo[0].seat`
  - [0].level：JSON路径 `$.ed_petTeamInfo[0].level`；生成字段名 `personal.ed_petTeamInfo[0].level`

**参数：ed_petTeamType**

- 展示名称：阵容类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petTeamType
- 生成字段名：personal.ed_petTeamType
- 说明：阵容类型
- 原始数据类型：int
- 参数备注：1为常规布阵，2为灵兽乱斗布阵

## 事件：PetReset

**事件说明**

- 展示名称：灵兽重置
- 事件分类：灵兽
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petId**

- 展示名称：长老id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petId
- 生成字段名：personal.ed_petId
- 说明：长老id
- 原始数据类型：int
- 参数备注：灵兽id

**参数：ed_petLevel**

- 展示名称：长老等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petLevel
- 生成字段名：personal.ed_petLevel
- 说明：长老等级
- 原始数据类型：int
- 参数备注：灵兽重置前等级

## 事件：PetDrawLevelUp

**事件说明**

- 展示名称：灵兽孵化等级提升
- 事件分类：灵兽
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petDrawLevelBefore**

- 展示名称：提升前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petDrawLevelBefore
- 生成字段名：personal.ed_petDrawLevelBefore
- 说明：提升前等级
- 原始数据类型：int

**参数：ed_petDrawLevelAfter**

- 展示名称：提升后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petDrawLevelAfter
- 生成字段名：personal.ed_petDrawLevelAfter
- 说明：提升后等级
- 原始数据类型：int

## 事件：PetBattle

**事件说明**

- 展示名称：灵兽大乱斗匹配战斗
- 事件分类：灵兽乱斗
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_petBattleTeamAttack**

- 展示名称：挑战者灵兽阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petBattleTeamAttack
- 生成字段名：personal.ed_petBattleTeamAttack
- 说明：挑战者灵兽阵容
- 原始数据类型：object
- 参数备注：例如：[{"petid":10001,"seat":1,"level":55},{"petid":10002,"seat":2,"level":55},{"petid":10003,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].petid：JSON路径 `$.ed_petBattleTeamAttack[0].petid`；生成字段名 `personal.ed_petBattleTeamAttack[0].petid`
  - [0].seat：JSON路径 `$.ed_petBattleTeamAttack[0].seat`；生成字段名 `personal.ed_petBattleTeamAttack[0].seat`
  - [0].level：JSON路径 `$.ed_petBattleTeamAttack[0].level`；生成字段名 `personal.ed_petBattleTeamAttack[0].level`

**参数：ed_petBattleTeamDefence**

- 展示名称：被挑战者灵兽阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petBattleTeamDefence
- 生成字段名：personal.ed_petBattleTeamDefence
- 说明：被挑战者灵兽阵容
- 原始数据类型：object
- 参数备注：例如：[{"petid":10001,"seat":1,"level":55},{"petid":10002,"seat":2,"level":55},{"petid":10003,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].petid：JSON路径 `$.ed_petBattleTeamDefence[0].petid`；生成字段名 `personal.ed_petBattleTeamDefence[0].petid`
  - [0].seat：JSON路径 `$.ed_petBattleTeamDefence[0].seat`；生成字段名 `personal.ed_petBattleTeamDefence[0].seat`
  - [0].level：JSON路径 `$.ed_petBattleTeamDefence[0].level`；生成字段名 `personal.ed_petBattleTeamDefence[0].level`

**参数：ed_petExTeamEffect**

- 展示名称：挑战者啦啦队效果
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petExTeamEffect
- 生成字段名：personal.ed_petExTeamEffect
- 说明：挑战者啦啦队效果
- 原始数据类型：object
- 参数备注：格式为（稀有度,起效数值）例如：{"1":5,"2":5,"3":5,"4":5,"5":5}
- 已知子字段映射：
  - ["1"]：JSON路径 `$.ed_petExTeamEffect["1"]`；生成字段名 `personal.ed_petExTeamEffect["1"]`
  - ["2"]：JSON路径 `$.ed_petExTeamEffect["2"]`；生成字段名 `personal.ed_petExTeamEffect["2"]`
  - ["3"]：JSON路径 `$.ed_petExTeamEffect["3"]`；生成字段名 `personal.ed_petExTeamEffect["3"]`
  - ["4"]：JSON路径 `$.ed_petExTeamEffect["4"]`；生成字段名 `personal.ed_petExTeamEffect["4"]`
  - ["5"]：JSON路径 `$.ed_petExTeamEffect["5"]`；生成字段名 `personal.ed_petExTeamEffect["5"]`

**参数：ed_petNpc**

- 展示名称：对战目标是否NPC
- 数据类型：布尔值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petNpc
- 生成字段名：personal.ed_petNpc
- 说明：对战目标是否NPC
- 原始数据类型：bool
- 参数备注：0代表是，1代表不是

**参数：ed_petEnemyId**

- 展示名称：对战目标玩家id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petEnemyId
- 生成字段名：personal.ed_petEnemyId
- 说明：对战目标玩家id
- 原始数据类型：int
- 参数备注：如果为NPC则为0

**参数：ed_petBattleId**

- 展示名称：本次战斗唯一id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petBattleId
- 生成字段名：personal.ed_petBattleId
- 说明：本次战斗唯一id
- 原始数据类型：int
- 参数备注：本场战斗唯一id

**参数：ed_petArenaResult**

- 展示名称：本次挑战结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petArenaResult
- 生成字段名：personal.ed_petArenaResult
- 说明：本次挑战结果
- 原始数据类型：int
- 参数备注：根据挑战者结果，win/lose

**参数：ed_petArenaPointOld**

- 展示名称：本次挑战前积分
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petArenaPointOld
- 生成字段名：personal.ed_petArenaPointOld
- 说明：本次挑战前积分
- 原始数据类型：int
- 参数备注：玩家的积分

**参数：ed_petArenaPointchange**

- 展示名称：挑战者积分变化
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petArenaPointchange
- 生成字段名：personal.ed_petArenaPointchange
- 说明：挑战者积分变化
- 原始数据类型：int
- 参数备注：挑战后-挑战前的积分差值，0代表不变

**参数：ed_petArenaWinTime**

- 展示名称：挑战者连胜次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_petArenaWinTime
- 生成字段名：personal.ed_petArenaWinTime
- 说明：挑战者连胜次数
- 原始数据类型：int
- 参数备注：包含本次战斗结果的连胜次数，本次失败则为0

## 事件：PackageBuy

**事件说明**

- 展示名称：购买付费项目
- 事件分类：商业化
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_payId**

- 展示名称：订单号
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_payId
- 生成字段名：personal.ed_payId
- 说明：订单号
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_packageNumMax**

- 展示名称：最大购买次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_packageNumMax
- 生成字段名：personal.ed_packageNumMax
- 说明：最大购买次数
- 原始数据类型：int
- 参数备注：最大可购买次数，如果无限制则为-1

**参数：ed_packageNumAlready**

- 展示名称：已购买次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_packageNumAlready
- 生成字段名：personal.ed_packageNumAlready
- 说明：已购买次数
- 原始数据类型：int
- 参数备注：已购买次数（包含本次）

**参数：ed_packageId**

- 展示名称：礼包id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_packageId
- 生成字段名：personal.ed_packageId
- 说明：礼包id
- 原始数据类型：int
- 参数备注：recharge表的id

**参数：ed_packagePayNum**

- 展示名称：付费价格
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_packagePayNum
- 生成字段名：personal.ed_packagePayNum
- 说明：付费价格
- 原始数据类型：int
- 参数备注：单位为人民币

## 事件：XianzhouUnlock

**事件说明**

- 展示名称：仙舟解封
- 事件分类：仙舟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_xianzhouStage**

- 展示名称：当前完成阶段
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouStage
- 生成字段名：personal.ed_xianzhouStage
- 说明：当前完成阶段
- 原始数据类型：int
- 参数备注：xianZhou表对应阶段id

**参数：ed_xianzhouStageMain**

- 展示名称：当前阶段的大阶段
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouStageMain
- 生成字段名：personal.ed_xianzhouStageMain
- 说明：当前阶段的大阶段
- 原始数据类型：int
- 参数备注：xianZhou表对应阶段stage

**参数：ed_xianzhouStageCount**

- 展示名称：当前累计完成阶段数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouStageCount
- 生成字段名：personal.ed_xianzhouStageCount
- 说明：当前累计完成阶段数量
- 原始数据类型：int
- 参数备注：包含本次

## 事件：QiFuUpgrade

**事件说明**

- 展示名称：福缘升级
- 事件分类：祈福
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_qifuLevelOld**

- 展示名称：升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuLevelOld
- 生成字段名：personal.ed_qifuLevelOld
- 说明：升级前等级
- 原始数据类型：int

**参数：ed_qifuLevelNew**

- 展示名称：升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuLevelNew
- 生成字段名：personal.ed_qifuLevelNew
- 说明：升级后等级
- 原始数据类型：int

## 事件：QiFuSet

**事件说明**

- 展示名称：祈福结果操作
- 事件分类：祈福
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_qifuInfoOld**

- 展示名称：旧福缘信息
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuInfoOld
- 生成字段名：personal.ed_qifuInfoOld
- 说明：旧福缘信息
- 原始数据类型：string
- 参数备注：{"gridBasePros":"[{{id:2102,buffId:10023,baseValue:20,growValue:200}},{{id:2101,buffId:10022,baseValue:20,growValue:200}},{{id:2101,buffId:10032,baseValue:100,growValue:100}},{{id:2103,buffId:10034,baseValue:100,growValue:100}}]","qiFuShowId":2,"gridId":7}], ed_mainBuildingLevel=50, ed_qifuBuffLevel=1, ed_qifuLevel=1,

**参数：ed_qifuInfoNew**

- 展示名称：新福缘信息
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuInfoNew
- 生成字段名：personal.ed_qifuInfoNew
- 说明：新福缘信息
- 原始数据类型：string
- 参数备注：{"gridBasePros":"[{{id:2102,buffId:10023,baseValue:20,growValue:200}},{{id:2101,buffId:10022,baseValue:20,growValue:200}},{{id:2101,buffId:10032,baseValue:100,growValue:100}},{{id:2103,buffId:10034,baseValue:100,growValue:100}}]","qiFuShowId":2,"gridId":7}], ed_mainBuildingLevel=50, ed_qifuBuffLevel=1, ed_qifuLevel=1,

**参数：ed_qifuChange**

- 展示名称：是否替换旧福缘
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuChange
- 生成字段名：personal.ed_qifuChange
- 说明：是否替换旧福缘
- 原始数据类型：int
- 参数备注：1为替换，2为放弃

## 事件：QiFuDraw

**事件说明**

- 展示名称：进行祈福
- 事件分类：祈福
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_qifuBuffLevel**

- 展示名称：祈福等级（等级那个
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuBuffLevel
- 生成字段名：personal.ed_qifuBuffLevel
- 说明：祈福等级（等级那个
- 原始数据类型：int

**参数：ed_qifuLevel**

- 展示名称：福缘等级（几率那个
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuLevel
- 生成字段名：personal.ed_qifuLevel
- 说明：福缘等级（几率那个
- 原始数据类型：int

**参数：ed_qifuResult**

- 展示名称：祈福结果
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_qifuResult
- 生成字段名：personal.ed_qifuResult
- 说明：祈福结果
- 原始数据类型：string
- 参数备注：{"gridBasePros":"[{{id:2102,buffId:10023,baseValue:20,growValue:200}},{{id:2101,buffId:10022,baseValue:20,growValue:200}},{{id:2101,buffId:10032,baseValue:100,growValue:100}},{{id:2103,buffId:10034,baseValue:100,growValue:100}}]","qiFuShowId":2,"gridId":7}], ed_mainBuildingLevel=50, ed_qifuBuffLevel=1, ed_qifuLevel=1,

## 事件：PatrolRun

**事件说明**

- 展示名称：进行宗门巡视
- 事件分类：宗门巡视
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_patrolNum**

- 展示名称：本次巡视次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_patrolNum
- 生成字段名：personal.ed_patrolNum
- 说明：本次巡视次数
- 原始数据类型：int

**参数：ed_patrolNumRemain**

- 展示名称：巡视剩余次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_patrolNumRemain
- 生成字段名：personal.ed_patrolNumRemain
- 说明：巡视剩余次数
- 原始数据类型：int

## 事件：GuBaoCombine

**事件说明**

- 展示名称：古宝合成
- 事件分类：古宝
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guBaoQuality**

- 展示名称：古宝品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoQuality
- 生成字段名：personal.ed_guBaoQuality
- 说明：古宝品质
- 原始数据类型：string

**参数：ed_guBaoId**

- 展示名称：古宝id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoId
- 生成字段名：personal.ed_guBaoId
- 说明：古宝id
- 原始数据类型：int

## 事件：GuBaoUpgrade

**事件说明**

- 展示名称：古宝升级
- 事件分类：古宝
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guBaoId**

- 展示名称：古宝id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoId
- 生成字段名：personal.ed_guBaoId
- 说明：古宝id
- 原始数据类型：int

**参数：ed_guBaoQuality**

- 展示名称：古宝品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoQuality
- 生成字段名：personal.ed_guBaoQuality
- 说明：古宝品质
- 原始数据类型：string

**参数：ed_guBaoStar**

- 展示名称：古宝星级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoStar
- 生成字段名：personal.ed_guBaoStar
- 说明：古宝星级
- 原始数据类型：string

**参数：ed_guBaoLevelOld**

- 展示名称：升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoLevelOld
- 生成字段名：personal.ed_guBaoLevelOld
- 说明：升级前等级
- 原始数据类型：int

**参数：ed_guBaoLevelNew**

- 展示名称：升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoLevelNew
- 生成字段名：personal.ed_guBaoLevelNew
- 说明：升级后等级
- 原始数据类型：int

## 事件：GuBaoStarUp

**事件说明**

- 展示名称：古宝升星
- 事件分类：古宝
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guBaoId**

- 展示名称：古宝id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoId
- 生成字段名：personal.ed_guBaoId
- 说明：古宝id
- 原始数据类型：int

**参数：ed_guBaoQuality**

- 展示名称：古宝品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoQuality
- 生成字段名：personal.ed_guBaoQuality
- 说明：古宝品质
- 原始数据类型：string

**参数：ed_guBaoLevel**

- 展示名称：古宝等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoLevel
- 生成字段名：personal.ed_guBaoLevel
- 说明：古宝等级
- 原始数据类型：string

**参数：ed_guBaoStarOld**

- 展示名称：升星前星级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoStarOld
- 生成字段名：personal.ed_guBaoStarOld
- 说明：升星前星级
- 原始数据类型：int

**参数：ed_guBaoStarNew**

- 展示名称：升星后星级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoStarNew
- 生成字段名：personal.ed_guBaoStarNew
- 说明：升星后星级
- 原始数据类型：int

## 事件：GuBaoTeam

**事件说明**

- 展示名称：古宝羁绊激活/升级
- 事件分类：古宝
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_guBaoTeamId**

- 展示名称：古宝羁绊id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoTeamId
- 生成字段名：personal.ed_guBaoTeamId
- 说明：古宝羁绊id
- 原始数据类型：int

**参数：ed_guBaoTeamLevelOld**

- 展示名称：升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoTeamLevelOld
- 生成字段名：personal.ed_guBaoTeamLevelOld
- 说明：升级前等级
- 原始数据类型：int
- 参数备注：如果未激活则为0

**参数：ed_guBaoTeamLevelNew**

- 展示名称：升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_guBaoTeamLevelNew
- 生成字段名：personal.ed_guBaoTeamLevelNew
- 说明：升级后等级
- 原始数据类型：int

## 事件：ZhiJiGet

**事件说明**

- 展示名称：知己激活
- 事件分类：知己
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_zhiJiId**

- 展示名称：知己id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiId
- 生成字段名：personal.ed_zhiJiId
- 说明：知己id
- 原始数据类型：int

**参数：ed_zhiJiQuality**

- 展示名称：知己品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiQuality
- 生成字段名：personal.ed_zhiJiQuality
- 说明：知己品质
- 原始数据类型：string

**参数：ed_zhiJiCount**

- 展示名称：知己数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiCount
- 生成字段名：personal.ed_zhiJiCount
- 说明：知己数量
- 原始数据类型：int
- 参数备注：包含本次激活的这个

## 事件：ZhiJiGift

**事件说明**

- 展示名称：知己送礼
- 事件分类：知己
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_zhiJiId**

- 展示名称：知己id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiId
- 生成字段名：personal.ed_zhiJiId
- 说明：知己id
- 原始数据类型：int

**参数：ed_zhiJiQuality**

- 展示名称：知己品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiQuality
- 生成字段名：personal.ed_zhiJiQuality
- 说明：知己品质
- 原始数据类型：string

**参数：ed_zhiJiPointChange**

- 展示名称：好感度变化值
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiPointChange
- 生成字段名：personal.ed_zhiJiPointChange
- 说明：好感度变化值
- 原始数据类型：int

**参数：ed_zhiJiLevelBefore**

- 展示名称：送礼前好感度等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiLevelBefore
- 生成字段名：personal.ed_zhiJiLevelBefore
- 说明：送礼前好感度等级
- 原始数据类型：int

**参数：ed_zhiJiLevelAfter**

- 展示名称：送礼后好感度等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiLevelAfter
- 生成字段名：personal.ed_zhiJiLevelAfter
- 说明：送礼后好感度等级
- 原始数据类型：int

**参数：ed_giftNum**

- 展示名称：本次送礼次数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_giftNum
- 生成字段名：personal.ed_giftNum
- 说明：本次送礼次数
- 原始数据类型：int
- 参数备注：记录本次送礼次数 单次赠送1 10连赠送10 100连赠送 100

**参数：ed_giftCost**

- 展示名称：礼物消耗
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_giftCost
- 生成字段名：personal.ed_giftCost
- 说明：礼物消耗
- 原始数据类型：object
- 参数备注：用json格式对象组记录物品id和数量即可， [{"itemid":"10001","num":10},{"itemid":"10002","num":10}]
- 已知子字段映射：
  - [0].itemid：JSON路径 `$.ed_giftCost[0].itemid`；生成字段名 `personal.ed_giftCost[0].itemid`
  - [0].num：JSON路径 `$.ed_giftCost[0].num`；生成字段名 `personal.ed_giftCost[0].num`

## 事件：ZhiJiSkillLevelUp

**事件说明**

- 展示名称：知己技能升级
- 事件分类：知己
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_zhiJiId**

- 展示名称：知己id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiId
- 生成字段名：personal.ed_zhiJiId
- 说明：知己id
- 原始数据类型：int

**参数：ed_zhiJiQuality**

- 展示名称：知己品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiQuality
- 生成字段名：personal.ed_zhiJiQuality
- 说明：知己品质
- 原始数据类型：string

**参数：ed_zhiJiLeve**

- 展示名称：当前好感度等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiLeve
- 生成字段名：personal.ed_zhiJiLeve
- 说明：当前好感度等级
- 原始数据类型：string

**参数：ed_zhiJiSkillId**

- 展示名称：知己技能id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiSkillId
- 生成字段名：personal.ed_zhiJiSkillId
- 说明：知己技能id
- 原始数据类型：string

**参数：ed_zhiJiSkillLevelBefore**

- 展示名称：升级前技能等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiSkillLevelBefore
- 生成字段名：personal.ed_zhiJiSkillLevelBefore
- 说明：升级前技能等级
- 原始数据类型：string

**参数：ed_zhiJiSkillLevelAfter**

- 展示名称：升级后技能等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_zhiJiSkillLevelAfter
- 生成字段名：personal.ed_zhiJiSkillLevelAfter
- 说明：升级后技能等级
- 原始数据类型：string

## 事件：ZhiJiSkin

**事件说明**

- 展示名称：知己皮肤激活
- 事件分类：知己
- 事件来源：后端
- 优先级：表格未注明

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_loverId**

- 展示名称：知己id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_loverId
- 生成字段名：personal.ed_loverId
- 说明：知己id
- 原始数据类型：int

**参数：ed_lzhiJiLevel**

- 展示名称：知己好感度等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_lzhiJiLevel
- 生成字段名：personal.ed_lzhiJiLevel
- 说明：知己好感度等级
- 原始数据类型：int

**参数：ed_skinId**

- 展示名称：知己皮肤id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_skinId
- 生成字段名：personal.ed_skinId
- 说明：知己皮肤id
- 原始数据类型：int

## 事件：ZhiJiSkinUpgrade

**事件说明**

- 展示名称：知己皮肤升级
- 事件分类：知己
- 事件来源：后端
- 优先级：表格未注明

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：edzhiJiId**

- 展示名称：知己id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.edzhiJiId
- 生成字段名：personal.edzhiJiId
- 说明：知己id
- 原始数据类型：int

**参数：ed_skinId**

- 展示名称：知己皮肤id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_skinId
- 生成字段名：personal.ed_skinId
- 说明：知己皮肤id
- 原始数据类型：int

**参数：ed_skinLevelBefore**

- 展示名称：知己皮肤等级（升级前）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_skinLevelBefore
- 生成字段名：personal.ed_skinLevelBefore
- 说明：知己皮肤等级（升级前）
- 原始数据类型：int

**参数：ed_skinLevelAfter**

- 展示名称：知己皮肤等级（升级后）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_skinLevelAfter
- 生成字段名：personal.ed_skinLevelAfter
- 说明：知己皮肤等级（升级后）
- 原始数据类型：int

**参数：ed_skinUpgradeCost**

- 展示名称：升级消耗
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_skinUpgradeCost
- 生成字段名：personal.ed_skinUpgradeCost
- 说明：升级消耗
- 原始数据类型：object
- 参数备注：用json格式对象组记录物品id和数量即可， [{"itemid":"10001","num":10},{"itemid":"10002","num":10}]
- 已知子字段映射：
  - [0].itemid：JSON路径 `$.ed_skinUpgradeCost[0].itemid`；生成字段名 `personal.ed_skinUpgradeCost[0].itemid`
  - [0].num：JSON路径 `$.ed_skinUpgradeCost[0].num`；生成字段名 `personal.ed_skinUpgradeCost[0].num`

## 事件：DongfuGetIn

**事件说明**

- 展示名称：占据洞府
- 事件分类：洞府
- 事件来源：后端
- 优先级：必打点
- 触发时机：每人每次占领都会触发

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_dongfuType**

- 展示名称：洞府类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuType
- 生成字段名：personal.ed_dongfuType
- 说明：洞府类型
- 原始数据类型：int
- 参数备注：dongfu表的dongfuType

**参数：ed_dongfuId**

- 展示名称：洞府id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuId
- 生成字段名：personal.ed_dongfuId
- 说明：洞府id
- 原始数据类型：int
- 参数备注：dongfu表的id

**参数：ed_dongFuXY**

- 展示名称：洞府坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongFuXY
- 生成字段名：personal.ed_dongFuXY
- 说明：洞府坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_dongfuBattleTeam**

- 展示名称：出征阵容
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuBattleTeam
- 生成字段名：personal.ed_dongfuBattleTeam
- 说明：出征阵容
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_dongfuBattleTeam[0].heroid`；生成字段名 `personal.ed_dongfuBattleTeam[0].heroid`
  - [0].seat：JSON路径 `$.ed_dongfuBattleTeam[0].seat`；生成字段名 `personal.ed_dongfuBattleTeam[0].seat`
  - [0].level：JSON路径 `$.ed_dongfuBattleTeam[0].level`；生成字段名 `personal.ed_dongfuBattleTeam[0].level`
  - [0].star：JSON路径 `$.ed_dongfuBattleTeam[0].star`；生成字段名 `personal.ed_dongfuBattleTeam[0].star`

**参数：ed_dongfuProgress**

- 展示名称：当前洞府总占据度
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgress
- 生成字段名：personal.ed_dongfuProgress
- 说明：当前洞府总占据度
- 原始数据类型：float
- 参数备注：例如：50% = 0.5

**参数：ed_dongfuProgressMe**

- 展示名称：当前洞府我的占据度
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgressMe
- 生成字段名：personal.ed_dongfuProgressMe
- 说明：当前洞府我的占据度
- 原始数据类型：float
- 参数备注：例如：50% = 0.5

**参数：ed_dongfuTeamNum**

- 展示名称：当前洞府队伍数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuTeamNum
- 生成字段名：personal.ed_dongfuTeamNum
- 说明：当前洞府队伍数
- 原始数据类型：int

## 事件：DongfuResult

**事件说明**

- 展示名称：洞府结算
- 事件分类：洞府
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_dongfuType**

- 展示名称：洞府类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuType
- 生成字段名：personal.ed_dongfuType
- 说明：洞府类型
- 原始数据类型：int
- 参数备注：dongfu表的dongfuType

**参数：ed_dongfuId**

- 展示名称：洞府id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuId
- 生成字段名：personal.ed_dongfuId
- 说明：洞府id
- 原始数据类型：int
- 参数备注：dongfu表的id

**参数：ed_dongFuXY**

- 展示名称：洞府坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongFuXY
- 生成字段名：personal.ed_dongFuXY
- 说明：洞府坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_dongfuRank**

- 展示名称：洞府占据度排行
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuRank
- 生成字段名：personal.ed_dongfuRank
- 说明：洞府占据度排行
- 原始数据类型：int
- 参数备注：第一名为1

**参数：ed_dongfuProgressMe**

- 展示名称：当前洞府我的占据度
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgressMe
- 生成字段名：personal.ed_dongfuProgressMe
- 说明：当前洞府我的占据度
- 原始数据类型：float
- 参数备注：例如：50% = 0.5

**参数：ed_dongfuResultNum**

- 展示名称：当前洞府获奖人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuResultNum
- 生成字段名：personal.ed_dongfuResultNum
- 说明：当前洞府获奖人数
- 原始数据类型：int

## 事件：CallBackTeam

**事件说明**

- 展示名称：撤回洞府队伍<br>（被人打回去）
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_teamInfoMe**

- 展示名称：撤回的阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfoMe
- 生成字段名：personal.ed_teamInfoMe
- 说明：撤回的阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfoMe[0].heroid`；生成字段名 `personal.ed_teamInfoMe[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfoMe[0].seat`；生成字段名 `personal.ed_teamInfoMe[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfoMe[0].level`；生成字段名 `personal.ed_teamInfoMe[0].level`
  - [0].star：JSON路径 `$.ed_teamInfoMe[0].star`；生成字段名 `personal.ed_teamInfoMe[0].star`

**参数：ed_dongfuType**

- 展示名称：洞府类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuType
- 生成字段名：personal.ed_dongfuType
- 说明：洞府类型
- 原始数据类型：int
- 参数备注：dongfu表的dongfuType

**参数：ed_dongfuId**

- 展示名称：洞府id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuId
- 生成字段名：personal.ed_dongfuId
- 说明：洞府id
- 原始数据类型：int
- 参数备注：dongfu表的id

**参数：ed_startXY**

- 展示名称：起点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_startXY
- 生成字段名：personal.ed_startXY
- 说明：起点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_targetXY**

- 展示名称：目标点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetXY
- 生成字段名：personal.ed_targetXY
- 说明：目标点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_dongfuProgress**

- 展示名称：当前洞府总占据度
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgress
- 生成字段名：personal.ed_dongfuProgress
- 说明：当前洞府总占据度
- 原始数据类型：float
- 参数备注：例如：50% = 0.5

**参数：ed_dongfuProgressMe**

- 展示名称：当前洞府我的占据度
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgressMe
- 生成字段名：personal.ed_dongfuProgressMe
- 说明：当前洞府我的占据度
- 原始数据类型：float
- 参数备注：例如：50% = 0.5

**参数：ed_dongfuTeamNum**

- 展示名称：当前洞府队伍数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuTeamNum
- 生成字段名：personal.ed_dongfuTeamNum
- 说明：当前洞府队伍数
- 原始数据类型：int

## 事件：XianzhouUpgrade

**事件说明**

- 展示名称：仙舟淬炼（升级/升阶）
- 事件分类：仙舟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_xianzhouSkinNum**

- 展示名称：已解锁仙舟皮肤数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouSkinNum
- 生成字段名：personal.ed_xianzhouSkinNum
- 说明：已解锁仙舟皮肤数量
- 原始数据类型：int

**参数：ed_xianzhouLevelOld**

- 展示名称：升级前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouLevelOld
- 生成字段名：personal.ed_xianzhouLevelOld
- 说明：升级前等级
- 原始数据类型：int

**参数：ed_xianzhouLevelNew**

- 展示名称：升级后等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouLevelNew
- 生成字段名：personal.ed_xianzhouLevelNew
- 说明：升级后等级
- 原始数据类型：int

## 事件：XianzhouSkinOn

**事件说明**

- 展示名称：仙舟皮肤解锁
- 事件分类：仙舟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_xianzhouSkinId**

- 展示名称：仙舟皮肤id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouSkinId
- 生成字段名：personal.ed_xianzhouSkinId
- 说明：仙舟皮肤id
- 原始数据类型：int

**参数：ed_xianzhouSkinQuality**

- 展示名称：仙舟皮肤品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouSkinQuality
- 生成字段名：personal.ed_xianzhouSkinQuality
- 说明：仙舟皮肤品质
- 原始数据类型：string

**参数：ed_xianzhouSkinNum**

- 展示名称：已解锁仙舟皮肤数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouSkinNum
- 生成字段名：personal.ed_xianzhouSkinNum
- 说明：已解锁仙舟皮肤数量
- 原始数据类型：int

**参数：ed_xianzhouLevel**

- 展示名称：仙舟当前等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouLevel
- 生成字段名：personal.ed_xianzhouLevel
- 说明：仙舟当前等级
- 原始数据类型：int

## 事件：VipLevelUp

**事件说明**

- 展示名称：vip等级提升
- 事件分类：VIP系统
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_vipLevelOld**

- 展示名称：升级前vip等级
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_vipLevelOld
- 生成字段名：personal.ed_vipLevelOld
- 说明：升级前vip等级

**参数：ed_vipLevelNew**

- 展示名称：升级后vip等级
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_vipLevelNew
- 生成字段名：personal.ed_vipLevelNew
- 说明：升级后vip等级

## 事件：ArmyHeal

**事件说明**

- 展示名称：开始治疗弟子
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_healNum**

- 展示名称：治疗数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNum
- 生成字段名：personal.ed_healNum
- 说明：治疗数量
- 原始数据类型：int

## 事件：ArmyHealCancel

**事件说明**

- 展示名称：取消治疗
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_healNumDone**

- 展示名称：已治疗数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumDone
- 生成字段名：personal.ed_healNumDone
- 说明：已治疗数量
- 原始数据类型：int

**参数：ed_healNumRemain**

- 展示名称：剩余未治疗弟子数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumRemain
- 生成字段名：personal.ed_healNumRemain
- 说明：剩余未治疗弟子数量
- 原始数据类型：int

## 事件：ArmyHealFinish

**事件说明**

- 展示名称：治疗弟子完成
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_healNumTime**

- 展示名称：本次治疗时长
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumTime
- 生成字段名：personal.ed_healNumTime
- 说明：本次治疗时长
- 原始数据类型：string

**参数：ed_healNumDone**

- 展示名称：本次治疗数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumDone
- 生成字段名：personal.ed_healNumDone
- 说明：本次治疗数量
- 原始数据类型：int

## 事件：ArmyHealAuto

**事件说明**

- 展示名称：自动治疗开启
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

## 事件：ArmyHealAutoFinish

**事件说明**

- 展示名称：取消自动治疗
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_healNumDone**

- 展示名称：已治疗数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumDone
- 生成字段名：personal.ed_healNumDone
- 说明：已治疗数量
- 原始数据类型：int
- 参数备注：本次自动治疗开启期间总计治疗数量

**参数：ed_healNumRemain**

- 展示名称：剩余未治疗弟子数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumRemain
- 生成字段名：personal.ed_healNumRemain
- 说明：剩余未治疗弟子数量
- 原始数据类型：int
- 参数备注：如果未自动结束则可能为0

## 事件：ArmyHealSpeedUp

**事件说明**

- 展示名称：治疗加速
- 事件分类：医院
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_healNumDone**

- 展示名称：本次治疗数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumDone
- 生成字段名：personal.ed_healNumDone
- 说明：本次治疗数量
- 原始数据类型：int

**参数：ed_healNumCost**

- 展示名称：本次治疗消耗
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_healNumCost
- 生成字段名：personal.ed_healNumCost
- 说明：本次治疗消耗
- 原始数据类型：object
- 参数备注：道具id和数量， {itemId:10001;number:2};{itemId:10002;number:3}...

## 事件：FriendDoList

**事件说明**

- 展示名称：好友操作
- 事件分类：好友
- 事件来源：后端
- 优先级：必打点
- 触发时机：批量操作发一条

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_doType**

- 展示名称：操作类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_doType
- 生成字段名：personal.ed_doType
- 说明：操作类型
- 原始数据类型：int
- 参数备注：1申请好友 ；2删除好友；3屏蔽（黑名单）；4解除屏蔽；<br>5通过好友申请；6收取友情点；7赠送友情点

**参数：ed_friendId**

- 展示名称：对方玩家id
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_friendId
- 生成字段名：personal.ed_friendId
- 说明：对方玩家id
- 原始数据类型：object
- 参数备注：玩家id 的list ["A", "B", "C"] ，包含一键批量操作
- 已知子字段映射：
  - [0]：JSON路径 `$.ed_friendId[0]`；生成字段名 `personal.ed_friendId[0]`

## 事件：FriendDeleteAll

**事件说明**

- 展示名称：一键删除
- 事件分类：好友
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_friendIdList**

- 展示名称：被删除的玩家id
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_friendIdList
- 生成字段名：personal.ed_friendIdList
- 说明：被删除的玩家id
- 原始数据类型：object
- 参数备注：玩家id 的list ["A", "B", "C"]
- 已知子字段映射：
  - [0]：JSON路径 `$.ed_friendIdList[0]`；生成字段名 `personal.ed_friendIdList[0]`

## 事件：AllianceGift

**事件说明**

- 展示名称：发送仙盟礼物
- 事件分类：仙盟
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_allianceOwnerId**

- 展示名称：盟主id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceOwnerId
- 生成字段名：personal.ed_allianceOwnerId
- 说明：盟主id
- 原始数据类型：string

**参数：ed_allianceLevel**

- 展示名称：仙盟等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceLevel
- 生成字段名：personal.ed_allianceLevel
- 说明：仙盟等级
- 原始数据类型：int
- 参数备注：捐献前等级

**参数：ed_allianceBoxLevel**

- 展示名称：仙盟礼物宝箱等级
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceBoxLevel
- 生成字段名：personal.ed_allianceBoxLevel
- 说明：仙盟礼物宝箱等级

**参数：ed_allianceGiftType**

- 展示名称：礼物类型
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceGiftType
- 生成字段名：personal.ed_allianceGiftType
- 说明：礼物类型
- 参数备注：0 普通礼物， 1 稀有礼物

**参数：ed_allianceGiftId**

- 展示名称：礼物ID
- 数据类型：表格未注明
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceGiftId
- 生成字段名：personal.ed_allianceGiftId
- 说明：礼物ID

## 事件：RadarLevelUp

**事件说明**

- 展示名称：雷达等级提升
- 事件分类：雷达
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_radarLevel**

- 展示名称：雷达等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_radarLevel
- 生成字段名：personal.ed_radarLevel
- 说明：雷达等级
- 原始数据类型：int
- 参数备注：升级后雷达等级

## 事件：RadarFinish

**事件说明**

- 展示名称：雷达任务结果
- 事件分类：雷达
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：radarTaskQuality**

- 展示名称：雷达任务品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskQuality
- 生成字段名：personal.radarTaskQuality
- 说明：雷达任务品质
- 原始数据类型：string

**参数：radarLevel**

- 展示名称：雷达等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarLevel
- 生成字段名：personal.radarLevel
- 说明：雷达等级
- 原始数据类型：string

**参数：radarTaskId**

- 展示名称：雷达任务id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskId
- 生成字段名：personal.radarTaskId
- 说明：雷达任务id
- 原始数据类型：string

**参数：result**

- 展示名称：结果
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.result
- 生成字段名：personal.result
- 说明：结果
- 原始数据类型：string
- 参数备注：0 胜利 1 失败

**参数：radarTargetType**

- 展示名称：雷达点类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTargetType
- 生成字段名：personal.radarTargetType
- 说明：雷达点类型
- 原始数据类型：string
- 参数备注：野怪 资源点等

## 事件：RadarNavigate

**事件说明**

- 展示名称：点击雷达点前往
- 事件分类：雷达
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：radarTaskQuality**

- 展示名称：雷达任务品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskQuality
- 生成字段名：personal.radarTaskQuality
- 说明：雷达任务品质
- 原始数据类型：string

**参数：radarLevel**

- 展示名称：雷达等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarLevel
- 生成字段名：personal.radarLevel
- 说明：雷达等级
- 原始数据类型：string

**参数：radarTaskId**

- 展示名称：雷达任务id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskId
- 生成字段名：personal.radarTaskId
- 说明：雷达任务id
- 原始数据类型：string

**参数：radarTargetType**

- 展示名称：雷达点类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTargetType
- 生成字段名：personal.radarTargetType
- 说明：雷达点类型
- 原始数据类型：string
- 参数备注：野怪 资源点等

## 事件：WorldTeamChange

**事件说明**

- 展示名称：储存沙盒阵容信息
- 事件分类：布阵
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_teamNum**

- 展示名称：阵容id（储存位）
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamNum
- 生成字段名：personal.ed_teamNum
- 说明：阵容id（储存位）
- 原始数据类型：int

**参数：ed_teamInfo**

- 展示名称：储存后阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfo
- 生成字段名：personal.ed_teamInfo
- 说明：储存后阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfo[0].heroid`；生成字段名 `personal.ed_teamInfo[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfo[0].seat`；生成字段名 `personal.ed_teamInfo[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfo[0].level`；生成字段名 `personal.ed_teamInfo[0].level`
  - [0].star：JSON路径 `$.ed_teamInfo[0].star`；生成字段名 `personal.ed_teamInfo[0].star`

**参数：ed_xianzhouId**

- 展示名称：所用仙舟ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouId
- 生成字段名：personal.ed_xianzhouId
- 说明：所用仙舟ID
- 原始数据类型：int

## 事件：TeamMove

**事件说明**

- 展示名称：沙盘出征
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_startXY**

- 展示名称：起点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_startXY
- 生成字段名：personal.ed_startXY
- 说明：起点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_targetXY**

- 展示名称：目标点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetXY
- 生成字段名：personal.ed_targetXY
- 说明：目标点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_startArea**

- 展示名称：起点区域ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_startArea
- 生成字段名：personal.ed_startArea
- 说明：起点区域ID
- 原始数据类型：string
- 参数备注：区域id

**参数：ed_marchType**

- 展示名称：出征类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_marchType
- 生成字段名：personal.ed_marchType
- 说明：出征类型
- 原始数据类型：string
- 参数备注：调动为0， 出征为1

**参数：ed_tragetType**

- 展示名称：目标类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_tragetType
- 生成字段名：personal.ed_tragetType
- 说明：目标类型
- 原始数据类型：string
- 参数备注：1资源点ok；2野怪ok；3雷达任务；4城市；5洞府ok

**参数：ed_targetId**

- 展示名称：目标配置id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetId
- 生成字段名：personal.ed_targetId
- 说明：目标配置id
- 原始数据类型：string
- 参数备注：城市：区域id 、资源点：资源id、野怪：野怪id、洞府：洞府id

**参数：ed_targetallianceId**

- 展示名称：目标当前所属联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetallianceId
- 生成字段名：personal.ed_targetallianceId
- 说明：目标当前所属联盟id
- 原始数据类型：string
- 参数备注：仅城市和洞府需要

**参数：ed_teamPower**

- 展示名称：出征部队总战力
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamPower
- 生成字段名：personal.ed_teamPower
- 说明：出征部队总战力
- 原始数据类型：string

**参数：ed_teamInfo**

- 展示名称：出征阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfo
- 生成字段名：personal.ed_teamInfo
- 说明：出征阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfo[0].heroid`；生成字段名 `personal.ed_teamInfo[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfo[0].seat`；生成字段名 `personal.ed_teamInfo[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfo[0].level`；生成字段名 `personal.ed_teamInfo[0].level`
  - [0].star：JSON路径 `$.ed_teamInfo[0].star`；生成字段名 `personal.ed_teamInfo[0].star`

**参数：ed_xianzhouId**

- 展示名称：所用仙舟ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouId
- 生成字段名：personal.ed_xianzhouId
- 说明：所用仙舟ID
- 原始数据类型：int

**参数：ed_resourceType**

- 展示名称：资源点类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceType
- 生成字段名：personal.ed_resourceType
- 说明：资源点类型
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_resourceLevel**

- 展示名称：资源点等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceLevel
- 生成字段名：personal.ed_resourceLevel
- 说明：资源点等级
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_ownResourceNum**

- 展示名称：当前已有的资源点数量
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ownResourceNum
- 生成字段名：personal.ed_ownResourceNum
- 说明：当前已有的资源点数量
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_monsterLevel**

- 展示名称：野怪等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_monsterLevel
- 生成字段名：personal.ed_monsterLevel
- 说明：野怪等级
- 原始数据类型：string
- 参数备注：仅野怪需要

**参数：ed_radarLevel**

- 展示名称：雷达等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_radarLevel
- 生成字段名：personal.ed_radarLevel
- 说明：雷达等级
- 原始数据类型：string
- 参数备注：仅雷达需要

**参数：radarTaskQuality**

- 展示名称：雷达任务品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskQuality
- 生成字段名：personal.radarTaskQuality
- 说明：雷达任务品质
- 原始数据类型：string
- 参数备注：仅雷达需要

**参数：ed_battleMode**

- 展示名称：攻防行为
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleMode
- 生成字段名：personal.ed_battleMode
- 说明：攻防行为
- 原始数据类型：string
- 参数备注：0攻击，1防守，仅城市需要

**参数：ed_cityStatus**

- 展示名称：城市状态
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cityStatus
- 生成字段名：personal.ed_cityStatus
- 说明：城市状态
- 原始数据类型：string
- 参数备注：仅城市需要   （0 交战状态 / 1 保护状态）

**参数：ed_RemainArmyNum**

- 展示名称：目标点守军数量
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_RemainArmyNum
- 生成字段名：personal.ed_RemainArmyNum
- 说明：目标点守军数量
- 原始数据类型：string
- 参数备注：仅洞府和城市

**参数：ed_ifAutoAttackCity**

- 展示名称：是否为自动攻城
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ifAutoAttackCity
- 生成字段名：personal.ed_ifAutoAttackCity
- 说明：是否为自动攻城
- 原始数据类型：string
- 参数备注：仅城市需要    0是1否

**参数：ed_dongfuType**

- 展示名称：洞府类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuType
- 生成字段名：personal.ed_dongfuType
- 说明：洞府类型
- 原始数据类型：string
- 参数备注：仅洞府需要

**参数：ed_dongfuProgress**

- 展示名称：当前总占据度
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgress
- 生成字段名：personal.ed_dongfuProgress
- 说明：当前总占据度
- 原始数据类型：string
- 参数备注：仅洞府需要

**参数：ed_dongfuProgressMe**

- 展示名称：当前我的占据度
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgressMe
- 生成字段名：personal.ed_dongfuProgressMe
- 说明：当前我的占据度
- 原始数据类型：string
- 参数备注：仅洞府需要

## 事件：TeamBattle

**事件说明**

- 展示名称：沙盘战斗
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：仙盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：仙盟id
- 原始数据类型：string

**参数：ed_battleXY**

- 展示名称：战斗点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleXY
- 生成字段名：personal.ed_battleXY
- 说明：战斗点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_startArea**

- 展示名称：起点区域ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_startArea
- 生成字段名：personal.ed_startArea
- 说明：起点区域ID
- 原始数据类型：string
- 参数备注：区域id

**参数：ed_marchType**

- 展示名称：出征类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_marchType
- 生成字段名：personal.ed_marchType
- 说明：出征类型
- 原始数据类型：string
- 参数备注：调动为0， 出征为1

**参数：ed_tragetType**

- 展示名称：目标类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_tragetType
- 生成字段名：personal.ed_tragetType
- 说明：目标类型
- 原始数据类型：string
- 参数备注：1资源点；2野怪OK；3雷达任务；4城市；5洞府ok

**参数：ed_targetId**

- 展示名称：目标配置id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetId
- 生成字段名：personal.ed_targetId
- 说明：目标配置id
- 原始数据类型：string
- 参数备注：城市：区域id 、资源点：资源id、野怪：野怪id、洞府：洞府id

**参数：ed_targetallianceId**

- 展示名称：目标当前所属联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetallianceId
- 生成字段名：personal.ed_targetallianceId
- 说明：目标当前所属联盟id
- 原始数据类型：string

**参数：ed_teamPower**

- 展示名称：出征部队总战力
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamPower
- 生成字段名：personal.ed_teamPower
- 说明：出征部队总战力
- 原始数据类型：string

**参数：ed_ifCombatNpc**

- 展示名称：实际发生战斗对象是否为npc
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ifCombatNpc
- 生成字段名：personal.ed_ifCombatNpc
- 说明：实际发生战斗对象是否为npc
- 原始数据类型：string
- 参数备注：0否，1是

**参数：ed_combatTargetId**

- 展示名称：实际发生战斗对象id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_combatTargetId
- 生成字段名：personal.ed_combatTargetId
- 说明：实际发生战斗对象id
- 原始数据类型：string
- 参数备注：假如实际发生战斗的是城市中的npc就传npcid 实际发生战斗的是城市中玩家就传uid

**参数：ed_teamInfoMe**

- 展示名称：我方阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfoMe
- 生成字段名：personal.ed_teamInfoMe
- 说明：我方阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfoMe[0].heroid`；生成字段名 `personal.ed_teamInfoMe[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfoMe[0].seat`；生成字段名 `personal.ed_teamInfoMe[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfoMe[0].level`；生成字段名 `personal.ed_teamInfoMe[0].level`
  - [0].star：JSON路径 `$.ed_teamInfoMe[0].star`；生成字段名 `personal.ed_teamInfoMe[0].star`

**参数：ed_teamInfoEnemy**

- 展示名称：敌方阵容信息
- 数据类型：对象
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamInfoEnemy
- 生成字段名：personal.ed_teamInfoEnemy
- 说明：敌方阵容信息
- 原始数据类型：object
- 参数备注：例如：[{"heroid":10001,"seat":1,"level":55,"star":15},{"heroid":10002,"seat":2,"level":55,"star":15},{"heroid":10003,"seat":3,"level":55,"star":15},{"heroid":10004,"seat":4,"level":55,"star":15},{"heroid":10005,"seat":6,"level":55,"star":15},{"petid":10005,"seat":1,"level":55},{"petid":10005,"seat":2,"level":55},{"petid":10005,"seat":3,"level":55}]
- 已知子字段映射：
  - [0].heroid：JSON路径 `$.ed_teamInfoEnemy[0].heroid`；生成字段名 `personal.ed_teamInfoEnemy[0].heroid`
  - [0].seat：JSON路径 `$.ed_teamInfoEnemy[0].seat`；生成字段名 `personal.ed_teamInfoEnemy[0].seat`
  - [0].level：JSON路径 `$.ed_teamInfoEnemy[0].level`；生成字段名 `personal.ed_teamInfoEnemy[0].level`
  - [0].star：JSON路径 `$.ed_teamInfoEnemy[0].star`；生成字段名 `personal.ed_teamInfoEnemy[0].star`

**参数：ed_battleResult**

- 展示名称：战斗结果
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleResult
- 生成字段名：personal.ed_battleResult
- 说明：战斗结果
- 原始数据类型：int
- 参数备注：0我方获胜，1敌方获胜，2平局

**参数：ed_battleDead**

- 展示名称：战斗损伤弟子
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleDead
- 生成字段名：personal.ed_battleDead
- 说明：战斗损伤弟子
- 原始数据类型：string
- 参数备注：弟子数量

**参数：ed_battleGroupId**

- 展示名称：战斗组ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleGroupId
- 生成字段名：personal.ed_battleGroupId
- 说明：战斗组ID
- 原始数据类型：int
- 参数备注：我方参与的连续的战斗算作同一组

**参数：ed_xianzhouId**

- 展示名称：我方所用仙舟ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouId
- 生成字段名：personal.ed_xianzhouId
- 说明：我方所用仙舟ID
- 原始数据类型：int

**参数：ed_resourceType**

- 展示名称：资源点类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceType
- 生成字段名：personal.ed_resourceType
- 说明：资源点类型
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_resourceLevel**

- 展示名称：资源点等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceLevel
- 生成字段名：personal.ed_resourceLevel
- 说明：资源点等级
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_ownResourceNum**

- 展示名称：当前已有的资源点数量
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ownResourceNum
- 生成字段名：personal.ed_ownResourceNum
- 说明：当前已有的资源点数量
- 原始数据类型：string
- 参数备注：仅资源点需要

**参数：ed_monsterLevel**

- 展示名称：野怪等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_monsterLevel
- 生成字段名：personal.ed_monsterLevel
- 说明：野怪等级
- 原始数据类型：string
- 参数备注：仅野怪需要

**参数：ed_radarLevel**

- 展示名称：雷达等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_radarLevel
- 生成字段名：personal.ed_radarLevel
- 说明：雷达等级
- 原始数据类型：string
- 参数备注：仅雷达需要

**参数：radarTaskQuality**

- 展示名称：雷达任务品质
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.radarTaskQuality
- 生成字段名：personal.radarTaskQuality
- 说明：雷达任务品质
- 原始数据类型：string
- 参数备注：仅雷达需要

**参数：ed_battleMode**

- 展示名称：攻防行为
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_battleMode
- 生成字段名：personal.ed_battleMode
- 说明：攻防行为
- 原始数据类型：string
- 参数备注：0攻击，1防守，仅城市需要

**参数：ed_cityStatus**

- 展示名称：城市状态
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cityStatus
- 生成字段名：personal.ed_cityStatus
- 说明：城市状态
- 原始数据类型：string
- 参数备注：仅城市需要   （0 交战状态 / 1 保护状态）

**参数：ed_RemainArmyNum**

- 展示名称：目标点守军数量
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_RemainArmyNum
- 生成字段名：personal.ed_RemainArmyNum
- 说明：目标点守军数量
- 原始数据类型：string
- 参数备注：仅洞府和城市

**参数：ed_ifAutoAttackCity**

- 展示名称：是否为自动攻城
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ifAutoAttackCity
- 生成字段名：personal.ed_ifAutoAttackCity
- 说明：是否为自动攻城
- 原始数据类型：string
- 参数备注：仅城市需要    0是1否

**参数：ed_dongfuType**

- 展示名称：洞府类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuType
- 生成字段名：personal.ed_dongfuType
- 说明：洞府类型
- 原始数据类型：string
- 参数备注：仅洞府需要

**参数：ed_dongfuProgress**

- 展示名称：当前总占据度
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgress
- 生成字段名：personal.ed_dongfuProgress
- 说明：当前总占据度
- 原始数据类型：string
- 参数备注：仅洞府需要

**参数：ed_dongfuProgressMe**

- 展示名称：当前我的占据度
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_dongfuProgressMe
- 生成字段名：personal.ed_dongfuProgressMe
- 说明：当前我的占据度
- 原始数据类型：string
- 参数备注：仅洞府需要

## 事件：MapSearch

**事件说明**

- 展示名称：搜索
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_searchType**

- 展示名称：搜索内容类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_searchType
- 生成字段名：personal.ed_searchType
- 说明：搜索内容类型
- 原始数据类型：int
- 参数备注：0野怪，1资源

**参数：ed_searchSubType**

- 展示名称：搜索内容子类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_searchSubType
- 生成字段名：personal.ed_searchSubType
- 说明：搜索内容子类型
- 原始数据类型：string
- 参数备注：哪类野怪 哪类资源等

**参数：ed_searchLevel**

- 展示名称：搜索内容等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_searchLevel
- 生成字段名：personal.ed_searchLevel
- 说明：搜索内容等级
- 原始数据类型：int

## 事件：SweepMonster

**事件说明**

- 展示名称：扫荡野怪
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_monsterId**

- 展示名称：野怪id
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_monsterId
- 生成字段名：personal.ed_monsterId
- 说明：野怪id
- 原始数据类型：int

**参数：ed_monsterLevel**

- 展示名称：野怪等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_monsterLevel
- 生成字段名：personal.ed_monsterLevel
- 说明：野怪等级
- 原始数据类型：int

## 事件：CallWar

**事件说明**

- 展示名称：城市争夺战宣战
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceJob**

- 展示名称：我的职级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJob
- 生成字段名：personal.ed_allianceJob
- 说明：我的职级
- 原始数据类型：int
- 参数备注：职级ID（盟主和副盟主）

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_occupiedCityNum**

- 展示名称：联盟当前已占领的城市数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_occupiedCityNum
- 生成字段名：personal.ed_occupiedCityNum
- 说明：联盟当前已占领的城市数量
- 原始数据类型：int

**参数：ed_type**

- 展示名称：类型
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_type
- 生成字段名：personal.ed_type
- 说明：类型
- 原始数据类型：string
- 参数备注：手动0   自动1

**参数：ed_targetCityArea**

- 展示名称：目标城市区域
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityArea
- 生成字段名：personal.ed_targetCityArea
- 说明：目标城市区域
- 原始数据类型：int
- 参数备注：区域ID

**参数：ed_targetCityBelong**

- 展示名称：目标城市归属
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityBelong
- 生成字段名：personal.ed_targetCityBelong
- 说明：目标城市归属
- 原始数据类型：int
- 参数备注：0为中立，如有联盟则为联盟id

**参数：ed_cityLevel**

- 展示名称：城市等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cityLevel
- 生成字段名：personal.ed_cityLevel
- 说明：城市等级
- 原始数据类型：string

**参数：ed_callNum**

- 展示名称：当前已宣战数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_callNum
- 生成字段名：personal.ed_callNum
- 说明：当前已宣战数量
- 原始数据类型：int
- 参数备注：包含本次宣战

## 事件：CallWarCancel

**事件说明**

- 展示名称：城市争夺战取消宣战
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceJob**

- 展示名称：我的职级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJob
- 生成字段名：personal.ed_allianceJob
- 说明：我的职级
- 原始数据类型：int
- 参数备注：职级ID（盟主和副盟主）

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_occupiedCityNum**

- 展示名称：联盟当前已占领的城市数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_occupiedCityNum
- 生成字段名：personal.ed_occupiedCityNum
- 说明：联盟当前已占领的城市数量
- 原始数据类型：int

**参数：ed_targetCityArea**

- 展示名称：目标城市区域
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityArea
- 生成字段名：personal.ed_targetCityArea
- 说明：目标城市区域
- 原始数据类型：int
- 参数备注：区域ID

**参数：ed_targetCityBelong**

- 展示名称：目标城市归属
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityBelong
- 生成字段名：personal.ed_targetCityBelong
- 说明：目标城市归属
- 原始数据类型：int
- 参数备注：0为中立，如有联盟则为联盟id

**参数：ed_cityLevel**

- 展示名称：城市等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cityLevel
- 生成字段名：personal.ed_cityLevel
- 说明：城市等级
- 原始数据类型：string

**参数：ed_callNum**

- 展示名称：当前已宣战数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_callNum
- 生成字段名：personal.ed_callNum
- 说明：当前已宣战数量
- 原始数据类型：int
- 参数备注：本次取消后的数量

## 事件：CityWarResult

**事件说明**

- 展示名称：城市争夺战战斗结果
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点
- 触发时机：参战的每个联盟每场城战发一条，默认挂在盟主身上发,无论胜负

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_targetCityArea**

- 展示名称：目标城市区域
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityArea
- 生成字段名：personal.ed_targetCityArea
- 说明：目标城市区域
- 原始数据类型：string
- 参数备注：区域ID

**参数：ed_targetCityBelong**

- 展示名称：目标城市原归属联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityBelong
- 生成字段名：personal.ed_targetCityBelong
- 说明：目标城市原归属联盟id
- 原始数据类型：string
- 参数备注：0为中立，如有联盟则为联盟id

**参数：ed_winAllianceId**

- 展示名称：争夺结束后城市所属联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_winAllianceId
- 生成字段名：personal.ed_winAllianceId
- 说明：争夺结束后城市所属联盟id
- 原始数据类型：string

**参数：ed_cityLevel**

- 展示名称：城市等级
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_cityLevel
- 生成字段名：personal.ed_cityLevel
- 说明：城市等级
- 原始数据类型：string

**参数：ed_ifFirstOccupy**

- 展示名称：是否是首占
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ifFirstOccupy
- 生成字段名：personal.ed_ifFirstOccupy
- 说明：是否是首占
- 原始数据类型：string
- 参数备注：0为非首占，1为首占

**参数：ed_occupiedCityNum**

- 展示名称：联盟当前已占领的城市数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_occupiedCityNum
- 生成字段名：personal.ed_occupiedCityNum
- 说明：联盟当前已占领的城市数量
- 原始数据类型：int

**参数：ed_sendingUserNum**

- 展示名称：自己联盟派兵的联盟人数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sendingUserNum
- 生成字段名：personal.ed_sendingUserNum
- 说明：自己联盟派兵的联盟人数
- 原始数据类型：int

**参数：ed_sendingTroopNum**

- 展示名称：自己联盟参加过战斗的部队数
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sendingTroopNum
- 生成字段名：personal.ed_sendingTroopNum
- 说明：自己联盟参加过战斗的部队数
- 原始数据类型：int

**参数：ed_sendingBattleNum**

- 展示名称：发生的城战战斗场次
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_sendingBattleNum
- 生成字段名：personal.ed_sendingBattleNum
- 说明：发生的城战战斗场次
- 原始数据类型：int

**参数：ed_result**

- 展示名称：战斗结果
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_result
- 生成字段名：personal.ed_result
- 说明：战斗结果
- 原始数据类型：string
- 参数备注：0为胜利归属我，1为失败不归属我

## 事件：CallGathering

**事件说明**

- 展示名称：设置集结标记
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceJob**

- 展示名称：我的职级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJob
- 生成字段名：personal.ed_allianceJob
- 说明：我的职级
- 原始数据类型：int
- 参数备注：职级ID（盟主和副盟主）

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_targetCityArea**

- 展示名称：目标城市区域
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityArea
- 生成字段名：personal.ed_targetCityArea
- 说明：目标城市区域
- 原始数据类型：int
- 参数备注：区域ID

**参数：ed_targetCityBelong**

- 展示名称：目标城市归属
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityBelong
- 生成字段名：personal.ed_targetCityBelong
- 说明：目标城市归属
- 原始数据类型：int
- 参数备注：0为中立，如有联盟则为联盟id

**参数：ed_gatheringType**

- 展示名称：集结类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_gatheringType
- 生成字段名：personal.ed_gatheringType
- 说明：集结类型
- 原始数据类型：int
- 参数备注：0为防御 1为进攻

## 事件：CancelGathering

**事件说明**

- 展示名称：取消集结标记
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_allianceJob**

- 展示名称：我的职级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceJob
- 生成字段名：personal.ed_allianceJob
- 说明：我的职级
- 原始数据类型：int
- 参数备注：职级ID（盟主和副盟主）

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_targetCityArea**

- 展示名称：目标城市区域
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityArea
- 生成字段名：personal.ed_targetCityArea
- 说明：目标城市区域
- 原始数据类型：int
- 参数备注：区域ID

**参数：ed_targetCityBelong**

- 展示名称：目标城市归属
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetCityBelong
- 生成字段名：personal.ed_targetCityBelong
- 说明：目标城市归属
- 原始数据类型：int
- 参数备注：0为中立，如有联盟则为联盟id

## 事件：GiveUpResource

**事件说明**

- 展示名称：放弃资源点
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_targetXY**

- 展示名称：资源点坐标
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_targetXY
- 生成字段名：personal.ed_targetXY
- 说明：资源点坐标
- 原始数据类型：string
- 参数备注：x,y

**参数：ed_ownResourceNum**

- 展示名称：当前已有的资源点数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_ownResourceNum
- 生成字段名：personal.ed_ownResourceNum
- 说明：当前已有的资源点数量
- 原始数据类型：int

**参数：ed_allianceId**

- 展示名称：联盟id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_allianceId
- 生成字段名：personal.ed_allianceId
- 说明：联盟id
- 原始数据类型：string

**参数：ed_resourceId**

- 展示名称：资源点ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceId
- 生成字段名：personal.ed_resourceId
- 说明：资源点ID
- 原始数据类型：string

**参数：ed_resourceType**

- 展示名称：资源点类型
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceType
- 生成字段名：personal.ed_resourceType
- 说明：资源点类型
- 原始数据类型：int

**参数：ed_resourceLevel**

- 展示名称：资源点等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_resourceLevel
- 生成字段名：personal.ed_resourceLevel
- 说明：资源点等级
- 原始数据类型：int

## 事件：SupplyTeamArmy

**事件说明**

- 展示名称：补充阵容缺失的弟子
- 事件分类：沙盘
- 事件来源：后端
- 优先级：必打点

**参数：ed_mainBuildingLevel**

- 展示名称：宗门等级
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_mainBuildingLevel
- 生成字段名：personal.ed_mainBuildingLevel
- 说明：宗门等级
- 原始数据类型：int
- 参数备注：如：20

**参数：ed_serverId**

- 展示名称：当前服务器ID
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_serverId
- 生成字段名：personal.ed_serverId
- 说明：当前服务器ID
- 原始数据类型：int
- 参数备注：默认-1

**参数：ed_teamNum**

- 展示名称：阵容id（储存位）
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_teamNum
- 生成字段名：personal.ed_teamNum
- 说明：阵容id（储存位）
- 原始数据类型：string

**参数：ed_xianzhouId**

- 展示名称：所用仙舟ID
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_xianzhouId
- 生成字段名：personal.ed_xianzhouId
- 说明：所用仙舟ID
- 原始数据类型：string

**参数：ed_armyId**

- 展示名称：弟子id
- 数据类型：文本
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_armyId
- 生成字段名：personal.ed_armyId
- 说明：弟子id
- 原始数据类型：string
- 参数备注：resource表对应id

**参数：ed_supplyNum**

- 展示名称：补充的弟子数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_supplyNum
- 生成字段名：personal.ed_supplyNum
- 说明：补充的弟子数量
- 原始数据类型：int

**参数：ed_supplyAfterNum**

- 展示名称：补充后弟子数量
- 数据类型：数值
- 数据源字段：personal
- 来源字段：personal
- JSON路径：$.ed_supplyAfterNum
- 生成字段名：personal.ed_supplyAfterNum
- 说明：补充后弟子数量
- 原始数据类型：int
