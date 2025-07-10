import icon_alybl_colorful from '@/assets/model/icon_alybl_colorful.png'
import icon_bdyzn_colorful from '@/assets/model/icon_bdyzn_colorful.png'
import icon_deepseek_colorful from '@/assets/model/icon_deepseek_colorful.png'
type ModelConfig = Record<number, { api_domain: string; model_options: string[] }>

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
        model_options: ['qwen-plus'],
      },
    },
  },
  {
    id: 2,
    name: '千帆大模型I',
    icon: icon_bdyzn_colorful,
    model_config: {
      0: {
        api_domain: 'https://qianfan.baidubce.com/v2/',
        model_options: ['ernie-x1-turbo-32k'],
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
        model_options: ['deepseek-chat', 'deepseek-reasoner'],
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
