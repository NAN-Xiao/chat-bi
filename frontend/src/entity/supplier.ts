import icon_alybl_colorful from '@/assets/model/icon_alybl_colorful.png'
import icon_bdyzn_colorful from '@/assets/model/icon_bdyzn_colorful.png'
import icon_deepseek_colorful from '@/assets/model/icon_deepseek_colorful.png'
import icon_txy_colorful from '@/assets/model/icon_txy_colorful.png'
import icon_xfhx_colorful from '@/assets/model/icon_xfhx_colorful.png'

type ModelArg = { key: string; val?: string | number; type: string; range?: string }
type ModelOption = { name: string; api_domain?: string; args?: ModelArg[] }
type ModelConfig = Record<
  number,
  { api_domain: string; common_args?: ModelArg[]; model_options: ModelOption[] }
>

export const supplierList: Array<{
  id: number
  name: string
  icon: any
  model_config: ModelConfig
}> = [
  {
    id: 1,
    name: '阿里云百炼',
    icon: icon_alybl_colorful,
    model_config: {
      0: {
        api_domain: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        model_options: [{ name: 'qwen-plus' }],
      },
    },
  },
  {
    id: 2,
    name: '千帆大模型',
    icon: icon_bdyzn_colorful,
    model_config: {
      0: {
        api_domain: 'https://qianfan.baidubce.com/v2/',
        model_options: [{ name: 'ernie-x1-turbo-32k' }],
      },
    },
  },
  {
    id: 3,
    name: 'DeepSeek',
    icon: icon_deepseek_colorful,
    model_config: {
      0: {
        api_domain: 'https://api.deepseek.com',
        model_options: [{ name: 'deepseek-chat' }, { name: 'deepseek-reasoner' }],
      },
    },
  },
  {
    id: 4,
    name: '腾讯云',
    icon: icon_txy_colorful,
    model_config: {
      0: {
        api_domain: 'https://api.hunyuan.cloud.tencent.com/v1/',
        model_options: [
          { name: 'hunyuan-turbos-latest' },
          { name: 'hunyuan-turbos-longtext-128k-20250325' },
          { name: 'hunyuan-large' },
          { name: 'hunyuan-standard-256K' },
          { name: 'hunyuan-standard' },
          { name: 'hunyuan-lite' },
        ],
      },
    },
  },
  {
    id: 5,
    name: '讯飞星火',
    icon: icon_xfhx_colorful,
    model_config: {
      0: {
        api_domain: 'https://spark-api-open.xf-yun.com/v1/',
        common_args: [{ key: 'temperature', val: 1.0, type: 'number', range: '[0, 2]' }],
        model_options: [
          {
            name: '4.0Ultra',
            args: [{ key: 'max_tokens', val: 32768, type: 'number', range: '[1, 32768]' }],
          },
          {
            name: 'generalv3.5',
            args: [{ key: 'max_tokens', val: 4096, type: 'number', range: '[1, 8192]' }],
          },
          {
            name: 'max-32k',
            args: [{ key: 'max_tokens', val: 4096, type: 'number', range: '[1, 32768]' }],
          },
          {
            name: 'generalv3',
            args: [{ key: 'max_tokens', val: 4096, type: 'number', range: '[1, 8192]' }],
          },
          {
            name: 'pro-128k',
            args: [{ key: 'max_tokens', val: 4096, type: 'number', range: '[1, 131072]' }],
          },
          {
            name: 'lite',
            args: [{ key: 'max_tokens', val: 4096, type: 'number', range: '[1, 4096]' }],
          },
          {
            name: 'x1',
            args: [
              { key: 'max_tokens', val: 32768, type: 'number', range: '[1, 32768]' },
              { key: 'temperature', val: 1.2, type: 'number', range: '(0, 2]' },
            ],
            api_domain: 'https://spark-api-open.xf-yun.com/v2/',
          },
        ],
      },
    },
  },
]

export const base_model_options = (supplier_id: number, model_type?: number) => {
  const supplier = get_supplier(supplier_id)
  return supplier?.model_config[model_type || 0].model_options
}

export const get_supplier = (supplier_id: number) => {
  return supplierList.find((item: any) => item.id === supplier_id)
}
