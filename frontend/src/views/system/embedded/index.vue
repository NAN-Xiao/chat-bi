<script lang="ts" setup>
import { ref, computed, reactive } from 'vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import icon_database_colorful from '@/assets/embedded/icon_database_colorful.png'
import icon_web_site_colorful from '@/assets/embedded/icon_web-site_colorful.png'
import Card from './Card.vue'
import DsCard from './DsCard.vue'
import { datasourceApi } from '@/api/datasource'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'

const { t } = useI18n()
const keywords = ref('')
const activeStep = ref(0)
const ruleConfigvVisible = ref(false)
const advancedApplication = ref(false)
const editRule = ref(0)
const embeddedFormRef = ref()
const dsFormRef = ref()
const urlFormRef = ref()
const dialogTitle = ref('')
const embeddedList = ref<any[]>([])
const systemCredentials = ref<any[]>([])
const credentials = ref<any[]>([])
const workspaces = ref<any[]>([])

const defaultEmbedded = {
  id: '',
  name: '',
  isBase: false,
  description: '',
  domain: '',
}
const currentEmbedded = reactive<any>(cloneDeep(defaultEmbedded))

const isCreate = ref(false)
const defaultForm = {
  workspace: '',
  id: '',
}
const dsForm = reactive(cloneDeep(defaultForm))

const defaultUrlForm = {
  url: '',
  system_credential_type: '',
  target_credential_location: '',
  credential_name: '',
  target_credential_name: '',
  target_credential: '',
  id: '',
}
const urlForm = reactive(cloneDeep(defaultUrlForm))

const dsListOptions = ref<any[]>([])

const embeddedListWithSearch = computed(() => {
  if (!keywords.value) return embeddedList.value
  return embeddedList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})

const userTypeList = [
  {
    name: t('embedded.basic_application'),
    img: icon_database_colorful,
    tip: t('embedded.support_is_required'),
    value: 1,
  },
  {
    name: t('embedded.advanced_application'),
    img: icon_web_site_colorful,
    tip: t('embedded.data_permissions_etc'),
    value: 0,
  },
]
const ruleType = ref(0)
const handleAddEmbedded = (val: any) => {
  ruleType.value = val
  Object.assign(currentEmbedded, cloneDeep(defaultEmbedded))
  if (val === 1) {
    handleBaseEmbedded(null)
  } else {
    handleAdvancedEmbedded(null)
  }
}

const getDsList = () => {
  datasourceApi.list().then((res: any) => {
    dsListOptions.value = res || []
  })
}
const handleBaseEmbedded = (row: any) => {
  advancedApplication.value = false
  getDsList()
  if (row) {
    Object.assign(dsForm, cloneDeep(defaultForm))
    // const { name, ds_id, table_id, tree, id, ds_name, table_name } = row
    // Object.assign(dsForm, {
    //   id,
    //   name,
    //   ds_id,
    //   table_id,
    //   ds_name,
    //   table_name,
    //   expression_tree: typeof tree === 'object' ? tree : JSON.parse(tree),
    // })
  }
  ruleConfigvVisible.value = true
  dialogTitle.value = row?.id
    ? t('embedded.edit_basic_applications')
    : t('embedded.create_basic_application')
}
const handleAdvancedEmbedded = (row: any) => {
  advancedApplication.value = true
  if (row) {
    Object.assign(urlForm, cloneDeep(defaultUrlForm))

    // const { name, ds_id, table_id, id, permission_list, ds_name, table_name } = row
    // Object.assign(dsForm, {
    //   id,
    //   name,
    //   ds_id,
    //   ds_name,
    //   table_id,
    //   table_name,
    //   permissions: permission_list,
    // })
  }
  ruleConfigvVisible.value = true
  dialogTitle.value = row?.id
    ? t('embedded.edit_advanced_applications')
    : t('embedded.creating_advanced_applications')
}

const beforeClose = () => {
  ruleConfigvVisible.value = false
  activeStep.value = 0
  isCreate.value = false
}

const handleActive = (row: any) => {
  console.log('row', row)
}

const handlePrivate = (row: any) => {
  console.log('row', row)
}
const handlePublic = (row: any) => {
  console.log('row', row)
}

const searchLoading = ref(false)
const handleSearch = () => {
  embeddedList.value = [
    {
      id: '1',
      name: 'jkajsdkjs',
      isBase: false,
      description: 'klasdkljlkasjdklljkajsdksa',
    },
    {
      id: '2',
      name: 'jkajsdkjsklk',
      isBase: true,
      description: 'kajldj',
    },
  ]
  // searchLoading.value = true
  //   getList()
  //     .then((res: any) => {
  //       embeddedList.value = res || []
  //     })
  //     .finally(() => {
  //       searchLoading.value = false
  //     })
}
handleSearch()

// const editForm = (row: any) => {
//   if (row.type === 'row') {
//     ruleType.value = 1
//     handleBaseEmbedded(row)
//   } else {
//     ruleType.value = 0
//     handleAdvancedEmbedded(row)
//   }
// }
const handleEditRule = (row: any) => {
  editRule.value = 1
  isCreate.value = false
  Object.assign(currentEmbedded, cloneDeep(row))
  ruleConfigvVisible.value = true
}

// const deleteRuleHandler = (row: any) => {
//   ElMessageBox.confirm(t('permission.rule_rule_1', { msg: row.name }), {
//     confirmButtonType: 'danger',
//     confirmButtonText: t('dashboard.delete'),
//     cancelButtonText: t('common.cancel'),
//     customClass: 'confirm-no_icon',
//     autofocus: false,
//   }).then(() => {
//     currentEmbedded.permissions = currentEmbedded.permissions.filter(
//       (ele: any) => ele.id !== row.id
//     )
//   })
// }

const deleteHandler = (row: any) => {
  ElMessageBox.confirm(t('permission.rule_group_1', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    // delPermissions(row.id).then(() => {
    //   ElMessage({
    //     type: 'success',
    //     message: t('dashboard.delete_success'),
    //   })
    //   handleSearch()
    // })
  })
}

const rules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('embedded.basic_information'),
      trigger: 'blur',
    },
  ],
  description: [
    {
      required: true,
      message:
        t('datasource.please_enter') + t('common.empty') + t('embedded.application_description'),
      trigger: 'blur',
    },
  ],
  domain: [
    {
      required: true,
      message:
        t('datasource.please_enter') + t('common.empty') + t('embedded.cross_domain_settings'),
      trigger: 'blur',
    },
  ],
}

const dsRules = {
  workspace: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.workspace'),
      trigger: 'change',
    },
  ],
}

const urlRules = {
  url: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('embedded.interface_url'),
      trigger: 'blur',
    },
  ],
  system_credential_type: [
    {
      required: true,
      message:
        t('datasource.Please_select') +
        t('common.empty') +
        t('embedded.target_credential_location'),
      trigger: 'change',
    },
  ],
  credential_name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('embedded.credential_name'),
      trigger: 'blur',
    },
  ],

  target_credential_location: [
    {
      required: true,
      message:
        t('datasource.Please_select') +
        t('common.empty') +
        t('embedded.target_credential_location'),
      trigger: 'change',
    },
  ],
  target_credential_name: [
    {
      required: true,
      message:
        t('datasource.please_enter') + t('common.empty') + t('embedded.target_credential_name'),
      trigger: 'blur',
    },
  ],

  target_credential: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('embedded.target_credential'),
      trigger: 'blur',
    },
  ],
}

// const closeForm = () => {
//   dialogFormVisible.value = false
// }
// const saveHandler = () => {
//   dsFormRef.value.validate((res: any) => {
//     if (res) {
//       dialogFormVisible.value = false
//     }
//   })
// }
const preview = () => {
  activeStep.value = 0
}
const next = () => {
  embeddedFormRef.value.validate((res: any) => {
    if (res) {
      activeStep.value = 1
    }
  })
}
const saveEmbedded = () => {
  //   const { id, name, permissions } = currentEmbedded
  //   saveEmbeddeds(permissions).then(() => {
  //     ElMessage({
  //       type: 'success',
  //       message: t('common.save_success'),
  //     })
  //     beforeClose()
  //     handleSearch()
  //   })
}
const btnSelect = ref('d')
</script>

<template>
  <div v-loading="searchLoading" class="permission">
    <div class="tool-left">
      <div class="btn-select">
        <el-button :class="[btnSelect === 'd' && 'is-active']" text @click="btnSelect = 'd'">
          {{ t('embedded.embedded_assistant') }}
        </el-button>
        <el-button :class="[btnSelect === 'q' && 'is-active']" text @click="btnSelect = 'q'">
          {{ t('embedded.embedded_page') }}
        </el-button>
      </div>
      <div>
        <el-input
          v-model="keywords"
          style="width: 240px; margin-right: 12px"
          :placeholder="$t('dashboard.search')"
          @keyup.enter="handleSearch"
          @blur="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>

        <el-popover popper-class="system-embedded_user" placement="bottom">
          <template #reference>
            <el-button type="primary">
              <template #icon>
                <icon_add_outlined></icon_add_outlined>
              </template>
              {{ $t('embedded.create_application') }}
            </el-button>
          </template>
          <div class="popover">
            <div class="popover-content">
              <div
                v-for="ele in userTypeList"
                :key="ele.name"
                class="popover-item"
                @click="handleAddEmbedded(ele.value)"
              >
                <img :src="ele.img" style="margin-top: 5px" width="32px" height="32px" />
                <div class="embedded">
                  <div class="name">{{ ele.name }}</div>
                  <div class="tip">{{ ele.tip }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-popover>
      </div>
    </div>

    <EmptyBackground
      v-if="!!keywords && !embeddedListWithSearch.length"
      :description="$t('datasource.relevant_content_found')"
      img-type="tree"
    />

    <div v-else class="card-content">
      <Card
        v-for="ele in embeddedListWithSearch"
        :id="ele.id"
        :key="ele.id"
        :name="ele.name"
        :is-base="ele.isBase"
        :description="ele.description"
        @edit="handleEditRule(ele)"
        @del="deleteHandler(ele)"
      ></Card>
    </div>
    <template v-if="!keywords && !embeddedListWithSearch.length && !searchLoading">
      <EmptyBackground :description="$t('embedded.no_application')" img-type="noneWhite" />

      <div style="text-align: center; margin-top: -10px">
        <el-popover popper-class="system-embedded_user" placement="bottom">
          <template #reference>
            <el-button type="primary">
              <template #icon>
                <icon_add_outlined></icon_add_outlined>
              </template>
              {{ $t('embedded.create_application') }}
            </el-button>
          </template>
          <div class="popover">
            <div class="popover-content">
              <div
                v-for="ele in userTypeList"
                :key="ele.name"
                class="popover-item"
                @click="handleAddEmbedded(ele.value)"
              >
                <img :src="ele.img" style="margin-top: 5px" width="32px" height="32px" />
                <div class="embedded">
                  <div class="name">{{ ele.name }}</div>
                  <div class="tip">{{ ele.tip }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-popover>
      </div>
    </template>
    <el-drawer
      v-model="ruleConfigvVisible"
      :close-on-click-modal="false"
      size="calc(100% - 100px)"
      modal-class="embedded-drawer-fullscreen"
      direction="btt"
      :before-close="beforeClose"
      :show-close="false"
    >
      <template #header="{ close }">
        <span style="white-space: nowrap">{{ dialogTitle }}</span>
        <div v-if="editRule !== 2" class="flex-center" style="width: 100%">
          <el-steps custom style="max-width: 500px; flex: 1" :active="activeStep" align-center>
            <el-step>
              <template #title> {{ $t('embedded.basic_information') }} </template>
            </el-step>
            <el-step>
              <template #title> {{ $t('embedded.set_data_source') }} </template>
            </el-step>
          </el-steps>
        </div>
        <el-icon style="cursor: pointer" @click="close">
          <icon_close_outlined></icon_close_outlined>
        </el-icon>
      </template>

      <div v-if="activeStep === 0" class="drawer-content">
        <div class="title">
          {{ $t('embedded.basic_information') }}
        </div>

        <el-form
          ref="embeddedFormRef"
          :model="currentEmbedded"
          label-width="180px"
          label-position="top"
          :rules="rules"
          class="form-content_error"
          @submit.prevent
        >
          <el-form-item prop="name" :label="t('embedded.basic_information')">
            <el-input
              v-model="currentEmbedded.name"
              :placeholder="
                $t('datasource.please_enter') +
                $t('common.empty') +
                $t('embedded.basic_information')
              "
              autocomplete="off"
            />
          </el-form-item>

          <el-form-item prop="description" :label="t('embedded.application_description')">
            <el-input
              v-model="currentEmbedded.description"
              :rows="3"
              type="textarea"
              :placeholder="$t('datasource.please_enter')"
              autocomplete="off"
            />
          </el-form-item>

          <el-form-item prop="domain" :label="t('embedded.cross_domain_settings')">
            <el-input
              v-model="currentEmbedded.domain"
              :placeholder="
                $t('datasource.please_enter') +
                $t('common.empty') +
                $t('embedded.third_party_address')
              "
              autocomplete="off"
            />
          </el-form-item>
        </el-form>
      </div>
      <div v-if="activeStep === 1 && advancedApplication" class="drawer-content">
        <div class="title">
          {{ $t('embedded.configure_interface') }}
        </div>

        <el-form
          ref="urlFormRef"
          :model="urlForm"
          label-width="180px"
          label-position="top"
          :rules="urlRules"
          class="form-content_error"
          @submit.prevent
        >
          <el-form-item prop="url" :label="t('embedded.interface_url')">
            <el-input
              v-model="urlForm.url"
              :placeholder="
                $t('datasource.please_enter') + $t('common.empty') + $t('embedded.interface_url')
              "
              autocomplete="off"
            />
          </el-form-item>
          <el-form-item prop="system_credential_type" :label="t('embedded.system_credential_type')">
            <el-select
              v-model="urlForm.system_credential_type"
              :placeholder="
                $t('datasource.Please_select') +
                $t('common.empty') +
                $t('embedded.target_credential_location')
              "
            >
              <el-option
                v-for="item in systemCredentials"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item prop="credential_name" :label="t('embedded.credential_name')">
            <el-input
              v-model="urlForm.credential_name"
              :placeholder="
                $t('datasource.please_enter') + $t('common.empty') + $t('embedded.credential_name')
              "
              autocomplete="off"
            />
          </el-form-item>
          <el-form-item
            prop="target_credential_location"
            :label="t('embedded.target_credential_location')"
          >
            <el-select
              v-model="urlForm.target_credential_location"
              :placeholder="
                $t('datasource.Please_select') +
                $t('common.empty') +
                $t('embedded.target_credential_location')
              "
            >
              <el-option
                v-for="item in credentials"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>

          <el-form-item prop="target_credential_name" :label="t('embedded.target_credential_name')">
            <el-input
              v-model="urlForm.target_credential_name"
              :placeholder="
                $t('datasource.please_enter') +
                $t('common.empty') +
                $t('embedded.target_credential_name')
              "
              autocomplete="off"
            />
          </el-form-item>

          <el-form-item prop="target_credential" :label="t('embedded.target_credential')">
            <el-input
              v-model="urlForm.target_credential"
              :placeholder="
                $t('datasource.please_enter') +
                $t('common.empty') +
                $t('embedded.target_credential')
              "
              autocomplete="off"
            />
          </el-form-item>
        </el-form>
      </div>
      <div v-if="activeStep === 1 && !advancedApplication" class="drawer-content">
        <div class="title">
          {{ $t('embedded.configure_interface') }}
        </div>

        <el-form
          ref="dsFormRef"
          :model="dsForm"
          label-width="180px"
          label-position="top"
          :rules="dsRules"
          class="form-content_error"
          @submit.prevent
        >
          <el-form-item prop="workspace" :label="t('user.workspace')">
            <el-select
              v-model="dsForm.workspace"
              :placeholder="
                $t('datasource.please_enter') + $t('common.empty') + $t('user.workspace')
              "
            >
              <el-option
                v-for="item in workspaces"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>

          <el-form-item prop="datasource" :label="t('embedded.set_data_source')">
            <div class="card-ds_content">
              <DsCard
                v-for="ele in dsListOptions"
                :id="ele.id"
                :key="ele.id"
                :name="ele.name"
                :type="ele.type"
                :type-name="ele.type_name"
                :is-private="ele.isPrivate"
                :num="ele.num"
                @active="handleActive(ele)"
                @private="handlePrivate(ele)"
                @public="handlePublic(ele)"
              ></DsCard>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button secondary @click="beforeClose"> {{ $t('common.cancel') }} </el-button>
        <el-button v-if="activeStep === 1 && editRule !== 2" secondary @click="preview">
          {{ t('ds.previous') }}
        </el-button>
        <el-button v-if="activeStep === 0 && editRule !== 2" type="primary" @click="next">
          {{ t('common.next') }}
        </el-button>
        <el-button v-if="activeStep === 1" type="primary" @click="saveEmbedded">
          {{ $t('common.save') }}
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.permission {
  .ed-empty {
    padding-top: 200px;
    padding-bottom: 0;
  }
  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    .btn-select {
      height: 32px;
      padding-left: 4px;
      padding-right: 4px;
      display: inline-flex;
      background: #ffffff;
      align-items: center;
      border: 1px solid #d9dcdf;
      border-radius: 6px;

      .is-active {
        background: #1cba901a;
      }

      .ed-button:not(.is-active) {
        color: #1f2329;
      }
      .ed-button.is-text {
        height: 24px;
        width: auto;
        padding: 0 8px;
        line-height: 24px;
      }
      .ed-button + .ed-button {
        margin-left: 4px;
      }
    }
  }

  .card-content {
    display: flex;
    flex-wrap: wrap;
    max-height: calc(100% - 40px);
    overflow-y: auto;
  }
}
</style>

<style lang="less">
.embedded-drawer-fullscreen {
  .title {
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
    margin-top: 8px;
    margin-bottom: 16px;
  }

  .card-ds_content {
    width: 100%;
    display: flex;
    align-items: center;
    flex-wrap: wrap;

    .card {
      width: 392px;
      &:nth-child(even) {
        margin-right: 0;
      }
    }
  }

  .drawer-content {
    width: 800px;
    margin: 0 auto;
    height: calc(100% - 20px);
  }
}

.system-embedded_user.system-embedded_user {
  padding: 0;
  width: 282px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .popover {
    .popover-content {
      padding: 4px;
      position: relative;
    }
    .popover-item {
      height: 98px;
      display: flex;
      padding-left: 12px;
      padding-right: 8px;
      position: relative;
      border-radius: 4px;
      cursor: pointer;
      &:hover {
        background: #1f23291a;
      }

      &:nth-child(2) {
        margin: 9px 0 0 0;
      }

      .embedded {
        font-weight: 400;
        margin-left: 8px;

        .name {
          font-size: 14px;
          line-height: 22px;
        }

        .tip {
          color: #8f959e;
          font-family: PingFang SC;
          font-size: 12px;
          line-height: 20px;
        }
      }
    }
  }
}
</style>
