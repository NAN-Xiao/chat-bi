<script lang="ts" setup>
import { computed, onMounted, provide, reactive, ref, unref } from 'vue'
import icon_info_outlined_1 from '@/assets/svg/icon_info_outlined_1.svg'
import { useI18n } from 'vue-i18n'
import { request } from '@/utils/request'
import { formatArg } from '@/utils/utils'
const { t } = useI18n()

const state = reactive({
  parameterForm: reactive<any>({
    'chat.shuzhi_name': '星通数智',
    'chat.expand_thinking_block': false,
    'chat.limit_rows': false,
    'chat.show_sql': false,
    'chat.show_log': false,
  }),
  feishuForm: reactive<any>({
    enable: false,
    valid: false,
    app_id: '',
    app_secret: '',
    redirect_uri: '',
    authorize_url: '',
    token_url: '',
    tenant_access_token_url: '',
    user_info_url: '',
    scope: '',
    token_mode: 'oauth_v2',
    secret_configured: false,
  }),
})
const feishuSaving = ref(false)
const feishuSubmitted = ref(false)
provide('parameterForm', state.parameterForm)

const requiredFeishuScopes = ['contact:user.base:readonly', 'contact:user.email:readonly']
const feishuRequiredEnabled = computed(() => Boolean(state.feishuForm.enable))

const cleanText = (value: unknown) => String(value ?? '').trim()

const isHttpUrl = (value: string) => {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const feishuValidationErrors = computed<Record<string, string>>(() => {
  const errors: Record<string, string> = {}

  if (!feishuRequiredEnabled.value) {
    return errors
  }

  const appId = cleanText(state.feishuForm.app_id)
  const appSecret = cleanText(state.feishuForm.app_secret)
  const scope = cleanText(state.feishuForm.scope)
  const scopeItems = scope.split(/\s+/).filter(Boolean)

  if (!appId) {
    errors.app_id = '启用企业飞书登录后必须填写 App ID'
  } else if (!/^cli_[A-Za-z0-9]+$/.test(appId)) {
    errors.app_id = 'App ID 格式应类似 cli_xxx'
  }

  if (!state.feishuForm.secret_configured && !appSecret) {
    errors.app_secret = '首次启用企业飞书登录必须填写 App Secret'
  }

  const urlFields: Array<[string, string]> = [
    ['redirect_uri', '回调地址'],
    ['authorize_url', '授权地址'],
    ['token_url', 'Token 地址'],
    ['user_info_url', '用户信息地址'],
  ]

  if (state.feishuForm.token_mode === 'authen_v1') {
    urlFields.push(['tenant_access_token_url', 'Tenant Access Token 地址'])
  }

  urlFields.forEach(([field, label]) => {
    const value = cleanText(state.feishuForm[field])
    if (!value) {
      errors[field] = `启用企业飞书登录后必须填写${label}`
    } else if (!isHttpUrl(value)) {
      errors[field] = `${label}必须是 http:// 或 https:// 开头的完整地址`
    }
  })

  if (!scope) {
    errors.scope = 'Scope 必须填写，至少包含用户基本信息和邮箱权限'
  } else {
    const missingScopes = requiredFeishuScopes.filter((item) => !scopeItems.includes(item))
    if (missingScopes.length > 0) {
      errors.scope = `Scope 缺少：${missingScopes.join('、')}`
    }
  }

  return errors
})

const hasFeishuValidationErrors = computed(() => Object.keys(feishuValidationErrors.value).length > 0)
const showFeishuValidation = computed(() => feishuSubmitted.value || feishuRequiredEnabled.value)

const feishuFieldClass = (field: string) => {
  return {
    'is-error': Boolean(showFeishuValidation.value && feishuValidationErrors.value[field]),
  }
}

const feishuFieldError = (field: string) => {
  if (!showFeishuValidation.value) {
    return ''
  }
  return feishuValidationErrors.value[field] || ''
}

const validateFeishuConfig = () => {
  feishuSubmitted.value = true
  if (hasFeishuValidationErrors.value) {
    ElMessage.error('企业飞书登录配置未完成，请先处理红色提示')
    return false
  }
  return true
}
const loadData = () => {
  request.get('/system/parameter').then((res: any) => {
    if (res) {
      res.forEach((item: any) => {
        if (
          item.pkey?.startsWith('chat') ||
          item.pkey?.startsWith('login') ||
          item.pkey?.startsWith('platform')
        ) {
          if (item.pkey === 'chat.shuzhi_name') {
            if (item.pval && item.pval.trim().length > 0) {
              state.parameterForm[item.pkey] = item.pval
            }
          } else {
            state.parameterForm[item.pkey] = formatArg(item.pval)
          }
        }
      })
      console.log(state.parameterForm)
    }
  })
}

const loadFeishuConfig = () => {
  request.get('/system/auth/feishu').then((res: any) => {
    Object.assign(state.feishuForm, {
      ...res,
      app_secret: '',
    })
  })
}

const onContextRecordCountChange = (count: number) => {
  if (count < 0) {
    state.parameterForm['chat.context_record_count'] = 0
  }
  state.parameterForm['chat.context_record_count'] = Math.floor(count)
}

const beforeChange = (): Promise<boolean> => {
  return new Promise((resolve) => {
    if (!state.parameterForm['chat.rows_of_data']) {
      return resolve(true)
    }
    ElMessageBox.confirm(t('parameter.excessive_data_volume'), t('parameter.prompt'), {
      confirmButtonType: 'primary',
      confirmButtonText: t('common.confirm2'),
      cancelButtonText: t('common.cancel'),
      customClass: 'confirm-no_icon confirm_no_icon_parameter',
      autofocus: false,
      callback: (action: any) => {
        resolve(action && action === 'confirm')
      },
    })
  })
}
const buildParam = () => {
  const changedItemArray = Object.keys(state.parameterForm).map((key: string) => {
    return {
      pkey: key,
      pval: Object.prototype.hasOwnProperty.call(state.parameterForm, 'key')
        ? state.parameterForm[key].toString()
        : state.parameterForm[key],
    }
  })
  const formData = new FormData()
  formData.append('data', JSON.stringify(unref(changedItemArray)))
  return formData
}
const saveHandler = () => {
  const param = buildParam()
  request
    .post('/system/parameter', param, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    .then(() => {
      ElMessage.success(t('common.save_success'))
    })
}
const saveFeishuHandler = () => {
  if (!validateFeishuConfig()) {
    return
  }
  feishuSaving.value = true
  const payload = {
    enable: Boolean(state.feishuForm.enable),
    app_id: state.feishuForm.app_id || '',
    app_secret: state.feishuForm.app_secret || null,
    redirect_uri: state.feishuForm.redirect_uri || '',
    authorize_url: state.feishuForm.authorize_url || '',
    token_url: state.feishuForm.token_url || '',
    tenant_access_token_url: state.feishuForm.tenant_access_token_url || '',
    user_info_url: state.feishuForm.user_info_url || '',
    scope: state.feishuForm.scope || null,
    token_mode: state.feishuForm.token_mode || 'oauth_v2',
  }
  request
    .put('/system/auth/feishu', payload)
    .then((res: any) => {
      Object.assign(state.feishuForm, {
        ...res,
        app_secret: '',
      })
      ElMessage.success(t('common.save_success'))
    })
    .finally(() => {
      feishuSaving.value = false
    })
}
onMounted(() => {
  loadData()
  loadFeishuConfig()
})
</script>

<template>
  <div class="parameter">
    <div class="title">
      {{ t('parameter.parameter_configuration') }}
    </div>
    <div class="card-container">
      <div class="card">
        <div class="card-title">
          {{ t('parameter.question_count_settings') }}
        </div>
        <el-row>
          <div class="card-item" style="width: 100%">
            <div class="label">
              {{ t('parameter.shuzhi_name') }}
            </div>
            <div class="value">
              <el-input v-model="state.parameterForm['chat.shuzhi_name']" />
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item">
            <div class="label">
              {{ t('parameter.model_thinking_process') }}

              <el-tooltip effect="dark" :content="t('parameter.closed_by_default')" placement="top">
                <el-icon size="16">
                  <icon_info_outlined_1></icon_info_outlined_1>
                </el-icon>
              </el-tooltip>
            </div>
            <div class="value">
              <el-switch v-model="state.parameterForm['chat.expand_thinking_block']" />
            </div>
          </div>
          <div class="card-item" style="margin-left: 16px">
            <div class="label">
              {{ t('parameter.rows_of_data') }}
              <el-tooltip
                effect="dark"
                :content="t('parameter.excessive_data_volume')"
                placement="top"
              >
                <el-icon size="16">
                  <icon_info_outlined_1></icon_info_outlined_1>
                </el-icon>
              </el-tooltip>
            </div>
            <div class="value">
              <el-switch
                v-model="state.parameterForm['chat.limit_rows']"
                :before-change="beforeChange"
              />
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item">
            <div class="label">
              {{ t('parameter.show_sql') }}
            </div>
            <div class="value">
              <el-switch v-model="state.parameterForm['chat.show_sql']" />
            </div>
          </div>
          <div class="card-item" style="margin-left: 16px">
            <div class="label">
              {{ t('parameter.show_log') }}
            </div>
            <div class="value">
              <el-switch v-model="state.parameterForm['chat.show_log']" />
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item">
            <div class="label">
              {{ t('parameter.context_record_count') }}
              <el-tooltip
                effect="dark"
                :content="t('parameter.context_record_count_hint')"
                placement="top"
              >
                <el-icon size="16">
                  <icon_info_outlined_1></icon_info_outlined_1>
                </el-icon>
              </el-tooltip>
            </div>
            <div class="value">
              <el-input-number
                v-model.number="state.parameterForm['chat.context_record_count']"
                min="0"
                step="1"
                @change="onContextRecordCountChange"
              />
            </div>
          </div>
        </el-row>
      </div>

      <div
        class="card feishu-config-card"
        :class="{ 'has-error': showFeishuValidation && hasFeishuValidationErrors }"
      >
        <div class="card-title">
          企业飞书登录配置
        </div>
        <div v-if="showFeishuValidation && hasFeishuValidationErrors" class="feishu-error-summary">
          企业飞书登录配置未完成，请检查红色标记的必填项和格式。
        </div>
        <el-row>
          <div class="card-item">
            <div class="label">启用企业飞书登录</div>
            <div class="value">
              <el-switch v-model="state.feishuForm.enable" />
            </div>
          </div>
          <div class="card-item" style="margin-left: 16px">
            <div class="label">配置状态</div>
            <div class="value feishu-valid-state" :class="{ valid: state.feishuForm.valid }">
              {{ state.feishuForm.valid ? '可用' : '未完成' }}
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item" :class="feishuFieldClass('app_id')">
            <div class="label"><span class="require">App ID</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.app_id" placeholder="cli_xxx" />
              <div v-if="feishuFieldError('app_id')" class="field-error">
                {{ feishuFieldError('app_id') }}
              </div>
            </div>
          </div>
          <div class="card-item" style="margin-left: 16px" :class="feishuFieldClass('app_secret')">
            <div class="label"><span class="require">App Secret</span></div>
            <div class="value">
              <el-input
                v-model="state.feishuForm.app_secret"
                type="password"
                show-password
                :placeholder="state.feishuForm.secret_configured ? '留空则保持当前密钥' : '请输入 App Secret'"
              />
              <div v-if="feishuFieldError('app_secret')" class="field-error">
                {{ feishuFieldError('app_secret') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item" style="width: 100%" :class="feishuFieldClass('redirect_uri')">
            <div class="label"><span class="require">回调地址</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.redirect_uri" />
              <div v-if="feishuFieldError('redirect_uri')" class="field-error">
                {{ feishuFieldError('redirect_uri') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item">
            <div class="label">Token 模式</div>
            <div class="value">
              <el-select v-model="state.feishuForm.token_mode" style="width: 100%">
                <el-option label="OAuth v2" value="oauth_v2" />
                <el-option label="Authen v1" value="authen_v1" />
              </el-select>
            </div>
          </div>
          <div class="card-item" style="margin-left: 16px" :class="feishuFieldClass('scope')">
            <div class="label"><span class="require">Scope</span></div>
            <div class="value">
              <el-input
                v-model="state.feishuForm.scope"
                placeholder="contact:user.base:readonly contact:user.email:readonly"
              />
              <div v-if="feishuFieldError('scope')" class="field-error">
                {{ feishuFieldError('scope') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item" style="width: 100%" :class="feishuFieldClass('authorize_url')">
            <div class="label"><span class="require">授权地址</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.authorize_url" />
              <div v-if="feishuFieldError('authorize_url')" class="field-error">
                {{ feishuFieldError('authorize_url') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item" style="width: 100%" :class="feishuFieldClass('token_url')">
            <div class="label"><span class="require">Token 地址</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.token_url" />
              <div v-if="feishuFieldError('token_url')" class="field-error">
                {{ feishuFieldError('token_url') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row v-if="state.feishuForm.token_mode === 'authen_v1'">
          <div
            class="card-item"
            style="width: 100%"
            :class="feishuFieldClass('tenant_access_token_url')"
          >
            <div class="label"><span class="require">Tenant Access Token 地址</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.tenant_access_token_url" />
              <div v-if="feishuFieldError('tenant_access_token_url')" class="field-error">
                {{ feishuFieldError('tenant_access_token_url') }}
              </div>
            </div>
          </div>
        </el-row>
        <el-row>
          <div class="card-item" style="width: 100%" :class="feishuFieldClass('user_info_url')">
            <div class="label"><span class="require">用户信息地址</span></div>
            <div class="value">
              <el-input v-model="state.feishuForm.user_info_url" />
              <div v-if="feishuFieldError('user_info_url')" class="field-error">
                {{ feishuFieldError('user_info_url') }}
              </div>
            </div>
          </div>
        </el-row>
        <div class="card-actions">
          <el-button type="primary" :loading="feishuSaving" @click="saveFeishuHandler">
            保存企业飞书登录配置
          </el-button>
        </div>
      </div>
    </div>
    <div class="save" style="margin-top: 16px">
      <el-button type="primary" @click="saveHandler">{{ t('common.save') }}</el-button>
    </div>
  </div>
</template>
<style lang="less">
.confirm_no_icon_parameter {
  .ed-message-box__header {
    margin-bottom: var(--ed-messagebox-padding-primary);
  }
  .ed-message-box__message > p {
    font-size: 14px;
    font-weight: 400;
    line-height: 22px;
  }
}
</style>
<style lang="less" scoped>
.parameter {
  :deep(.ed-radio) {
    --ed-radio-input-height: 16px;
    --ed-radio-input-width: 16px;
  }
  .title {
    font-weight: 500;
    font-size: 20px;
    line-height: 28px;
    margin-bottom: 16px;
  }
  .card-container {
    .card {
      width: 100%;
      border-radius: 12px;
      padding: 16px;
      border: 1px solid #dee0e3;
      display: flex;
      flex-direction: column;
      margin-top: 16px;

      .card-title {
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
        width: 100%;
      }
      .card-item {
        margin-top: 16px;
        width: calc(50% - 8px);
        .label {
          font-weight: 400;
          font-size: 14px;
          line-height: 22px;
          display: flex;
          align-items: center;

          .ed-icon {
            margin-left: 4px;
          }

          .require::after {
            content: '*';
            color: var(--ed-color-danger);
            margin-left: 4px;
          }
        }

        .value {
          margin-top: 8px;
          line-height: 20px;
        }
      }
      .card-actions {
        display: flex;
        justify-content: flex-end;
        margin-top: 16px;
      }
      &.feishu-config-card {
        transition:
          border-color 0.2s ease,
          box-shadow 0.2s ease;

        &.has-error {
          border-color: #ff4d4f;
          box-shadow: 0 0 0 1px rgba(255, 77, 79, 0.2);
        }

        .feishu-error-summary {
          margin-top: 12px;
          border: 1px solid #ffccc7;
          border-radius: 6px;
          padding: 9px 12px;
          background: #fff2f0;
          color: #cf1322;
          font-size: 13px;
          line-height: 20px;
        }

        .card-item.is-error {
          :deep(.ed-input__wrapper) {
            border-color: #ff4d4f;
            box-shadow: 0 0 0 1px #ff4d4f inset;
          }

          :deep(.ed-select .ed-input__wrapper) {
            border-color: #ff4d4f;
            box-shadow: 0 0 0 1px #ff4d4f inset;
          }
        }

        .field-error {
          margin-top: 6px;
          color: #cf1322;
          font-size: 12px;
          line-height: 18px;
        }
      }
      .feishu-valid-state {
        display: inline-flex;
        align-items: center;
        min-height: 32px;
        padding: 0 10px;
        border-radius: 6px;
        background: #fff7ed;
        color: #c2410c;
        font-size: 13px;
        font-weight: 600;

        &.valid {
          background: #ecfdf3;
          color: #047857;
        }
      }
    }
  }
}
</style>
