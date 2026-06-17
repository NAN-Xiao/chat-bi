<template>
  <div class="zhishu-table-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ $t('user.user_management') }}</span>
      <div class="search-bar">
        <el-input
          v-model="keyword"
          style="width: 240px; margin-right: 12px"
          :placeholder="$t('user.name_account_email')"
          clearable
          @keydown.enter.exact.prevent="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>

        <el-button secondary @click="drawerMainOpen">
          <template #icon>
            <iconFilter></iconFilter>
          </template>
          {{ $t('user.filter') }}
        </el-button>

        <!--  <el-button secondary @click="handleUserImport">
          <template #icon>
            <ccmUpload></ccmUpload>
          </template>
          {{ $t('user.batch_import') }}
        </el-button> -->
        <el-button type="primary" @click="editHandler(null)">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ $t('user.add_users') }}
        </el-button>
      </div>
    </div>
    <div
      class="zhishu-table_user"
      :class="[
        state.filterTexts.length && 'is-filter',
        multipleSelectionAll.length && 'show-pagination_height',
      ]"
    >
      <filter-text
        :total="state.pageInfo.total"
        :filter-texts="state.filterTexts"
        @clear-filter="clearFilter"
      />
      <el-table
        ref="multipleTableRef"
        :data="state.tableData"
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="name" show-overflow-tooltip :label="$t('user.name')" width="280" />
        <el-table-column
          prop="account"
          show-overflow-tooltip
          :label="$t('user.account')"
          width="280"
        />
        <el-table-column prop="status" :label="$t('user.user_status')" width="180">
          <template #default="scope">
            <div class="user-status-container" :class="[scope.row.status ? 'active' : 'disabled']">
              <el-icon size="16">
                <SuccessFilled v-if="scope.row.status" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span>{{ $t(`user.${scope.row.status ? 'enabled' : 'disabled'}`) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" show-overflow-tooltip :label="$t('user.email')" />
        <el-table-column prop="system_role" :label="$t('user.system_role')" width="140">
          <template #default="scope">
            <span
              class="system-role-text"
              :class="systemRoleClass(scope.row.system_role)"
            >
              {{ formatSystemRole(scope.row.system_role) }}
            </span>
          </template>
        </el-table-column>
        <!-- <el-table-column prop="phone" :label="$t('user.phone_number')" width="280" /> -->
        <el-table-column prop="origin" :label="$t('user.user_source')" width="120">
          <template #default="scope">
            <span>{{ formatUserOrigin(scope.row.origin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" width="180" sortable :label="$t('user.creation_time')">
          <template #default="scope">
            <span>{{ formatTimestamp(scope.row.create_time, 'YYYY-MM-DD HH:mm:ss') }}</span>
          </template>
        </el-table-column>
        <el-table-column fixed="right" width="150" :label="$t('ds.actions')">
          <template #default="scope">
            <div class="table-operate">
              <el-switch
                v-model="scope.row.status"
                :active-value="1"
                :inactive-value="0"
                :disabled="!canManageUserRole(scope.row)"
                size="small"
                @change="statusHandler(scope.row)"
              />
              <div class="line"></div>
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('datasource.edit')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="editHandler(scope.row)">
                  <IconOpeEdit></IconOpeEdit>
                </el-icon>
              </el-tooltip>

              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('common.reset_password')"
                placement="top"
              >
                <el-icon
                  :ref="
                    (el: any) => {
                      setButtonRef(el, scope.row)
                    }
                  "
                  v-click-outside="() => onClickOutside(scope.row)"
                  class="action-btn"
                  :class="{ disabled: !canManageUserRole(scope.row) }"
                  size="16"
                >
                  <IconLock></IconLock>
                </el-icon>
              </el-tooltip>
              <el-popover
                :ref="
                  (el: any) => {
                    setPopoverRef(el, scope.row)
                  }
                "
                placement="right"
                virtual-triggering
                :width="300"
                :virtual-ref="scope.row.buttonRef"
                trigger="click"
                show-arrow
              >
                <div class="reset-pwd-confirm">
                  <div class="confirm-header">
                    <span class="icon-span">
                      <el-icon size="24">
                        <icon_warning_filled class="svg-icon" />
                      </el-icon>
                    </span>
                    <span class="header-span">{{ t('datasource.the_original_one') }}</span>
                  </div>
                  <div class="confirm-content">
                    <span>{{ defaultPwd }}</span>
                    <el-button style="margin-left: 4px" text @click="copyText">{{
                      t('datasource.copy')
                    }}</el-button>
                  </div>
                  <div class="confirm-foot">
                    <el-button secondary @click="closeResetInfo(scope.row)">{{
                      t('common.cancel')
                    }}</el-button>
                    <el-button
                      type="primary"
                      :disabled="!canManageUserRole(scope.row)"
                      @click="handleEditPassword(scope.row)"
                    >
                      {{ t('datasource.confirm') }}
                    </el-button>
                  </div>
                </div>
              </el-popover>

              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('dashboard.delete')"
                placement="top"
              >
                <el-icon
                  class="action-btn"
                  :class="{ disabled: !canManageUserRole(scope.row) }"
                  size="16"
                  @click="deleteHandler(scope.row)"
                >
                  <IconOpeDelete></IconOpeDelete>
                </el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBackground
            v-if="!!keyword && !state.tableData.length"
            :description="$t('datasource.relevant_content_found')"
            img-type="tree"
          />
        </template>
      </el-table>
    </div>
    <div v-if="state.tableData.length" class="pagination-container">
      <el-pagination
        v-model:current-page="state.pageInfo.currentPage"
        v-model:page-size="state.pageInfo.pageSize"
        :page-sizes="[10, 20, 30]"
        :background="true"
        layout="total, sizes, prev, pager, next, jumper"
        :total="state.pageInfo.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>

    <div v-if="multipleSelectionAll.length" class="bottom-select">
      <el-checkbox
        v-model="checkAll"
        :indeterminate="isIndeterminate"
        @change="handleCheckAllChange"
      >
        {{ $t('datasource.select_all') }}
      </el-checkbox>

      <button class="danger-button" @click="deleteBatchUser">{{ $t('dashboard.delete') }}</button>

      <span class="selected">{{
        $t('user.selected_2_items', { msg: multipleSelectionAll.length })
      }}</span>

      <el-button text @click="cancelDelete">
        {{ $t('common.cancel') }}
      </el-button>
    </div>
  </div>

  <el-drawer
    v-model="dialogFormVisible"
    :title="dialogTitle"
    destroy-on-close
    modal-class="user-add-class"
    size="780px"
    :before-close="onFormClose"
  >
    <div style="margin-bottom: 12px" class="down-template">
      <span class="icon-span">
        <el-icon>
          <Icon name="icon_warning_filled"><icon_warning_filled class="svg-icon" /></Icon>
        </el-icon>
      </span>
      <div class="down-template-content" style="align-items: center">
        <span>{{ t('prompt.default_password', { msg: defaultPwd }) }}</span>
        <el-button style="margin-left: 4px" size="small" text @click="copyPassword">{{
          t('datasource.copy')
        }}</el-button>
      </div>
    </div>
    <el-form
      ref="termFormRef"
      :model="state.form"
      label-width="180px"
      label-position="top"
      :rules="rules"
      class="form-content_error"
      @submit.prevent
    >
      <el-form-item prop="name" :label="t('user.name')">
        <el-input
          v-model="state.form.name"
          :placeholder="$t('datasource.please_enter') + $t('common.empty') + $t('user.name')"
          autocomplete="off"
          maxlength="50"
          clearable
        />
      </el-form-item>
      <el-form-item prop="account" :label="t('user.account')">
        <el-input
          v-model="state.form.account"
          :disabled="!!state.form.id"
          :placeholder="$t('datasource.please_enter') + $t('common.empty') + $t('user.account')"
          autocomplete="off"
          maxlength="50"
          clearable
        />
      </el-form-item>
      <el-form-item prop="email" :label="$t('user.email')">
        <el-input
          v-model="state.form.email"
          :placeholder="$t('datasource.please_enter') + $t('common.empty') + $t('user.email')"
          autocomplete="off"
          clearable
        />
      </el-form-item>
      <el-form-item :label="$t('user.system_role')">
        <el-select
          v-model="state.form.system_role"
          popper-class="user-light-select-popper"
          style="width: 240px"
        >
          <el-option
            v-for="item in systemRoleOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="$t('user.project_permission_config')">
        <div class="project-permission-panel">
          <div class="project-permission-toolbar">
            <el-select
              v-model="state.form.project_ids"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              popper-class="user-light-select-popper"
              style="width: 420px"
              :placeholder="$t('user.select_accessible_projects')"
              @change="handleProjectIdsChange"
            >
              <el-option
                v-for="item in projectOptions"
                :key="item.id"
                :label="item.name"
                :value="Number(item.id)"
              />
            </el-select>
            <span class="project-permission-count">
              {{ $t('user.selected_project_count', { msg: selectedProjectRows.length }) }}
            </span>
          </div>

          <el-table
            :data="selectedProjectRows"
            :empty-text="$t('user.no_project_permission')"
            class="project-permission-table"
            style="width: 100%"
          >
            <el-table-column :label="$t('permission.data_source')" min-width="150">
              <template #default="scope">
                <div class="project-cell">
                  <div class="project-name ellipsis" :title="scope.row.name">
                    {{ scope.row.name }}
                  </div>
                  <div class="project-type ellipsis" :title="scope.row.type_name || scope.row.type">
                    {{ scope.row.type_name || scope.row.type || '-' }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="$t('user.database_scope')" min-width="150">
              <template #default="scope">
                <span class="database-label" :title="formatProjectDatabase(scope.row)">
                  {{ formatProjectDatabase(scope.row) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('user.project_role')" width="132">
              <template #default="scope">
                <el-select
                  v-model="state.form.project_role_map[Number(scope.row.id)]"
                  popper-class="user-light-select-popper"
                  style="width: 112px"
                >
                  <el-option
                    v-for="item in projectRoleOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="$t('user.permission_strategy')" min-width="220">
              <template #default="scope">
                <el-select
                  v-model="state.form.project_permission_map[Number(scope.row.id)]"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  popper-class="user-light-select-popper"
                  style="width: 100%"
                  :placeholder="$t('user.select_permission_strategy')"
                >
                  <el-option
                    v-for="item in getPermissionStrategiesByProject(scope.row.id)"
                    :key="item.id"
                    :label="item.name"
                    :value="Number(item.id)"
                  >
                    <div class="permission-option">
                      <span class="permission-option-name ellipsis" :title="item.name">
                        {{ item.name }}
                      </span>
                      <span class="permission-option-summary">
                        {{ formatRuleGroupSummary(item, scope.row.id) }}
                      </span>
                    </div>
                  </el-option>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="$t('user.permission_summary')" min-width="170">
              <template #default="scope">
                <div class="permission-summary">
                  <template v-if="getSelectedStrategiesByProject(scope.row.id).length">
                    <div class="summary-line" :title="formatTableAccessSummary(scope.row.id)">
                      {{ formatTableAccessSummary(scope.row.id) }}
                    </div>
                    <div class="summary-line" :title="formatFieldAccessSummary(scope.row.id)">
                      {{ formatFieldAccessSummary(scope.row.id) }}
                    </div>
                    <div class="summary-line" :title="formatRowAccessSummary(scope.row.id)">
                      {{ formatRowAccessSummary(scope.row.id) }}
                    </div>
                  </template>
                  <span v-else class="muted">{{ $t('user.project_access_only') }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="$t('user.user_status')" width="96">
              <template #default="scope">
                <el-tag
                  size="small"
                  :type="getSelectedStrategiesByProject(scope.row.id).length ? 'success' : 'info'"
                >
                  {{
                    getSelectedStrategiesByProject(scope.row.id).length
                      ? $t('user.strategy_configured')
                      : $t('user.no_strategy')
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('ds.actions')" width="76" fixed="right">
              <template #default="scope">
                <el-button text @click="removeProjectAccess(scope.row.id)">
                  {{ $t('project.remove') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-form-item>
      <!-- <el-form-item :label="$t('user.phone_number')">
        <el-input
          v-model="state.form.phoneNumber"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('user.phone_number')
          "
          autocomplete="off"
        />
      </el-form-item> -->

      <el-form-item>
        <template #label>
          <div style="display: flex; align-items: center; height: 22px">
            <span>{{ t('variables.system_variables') }}</span>
            <span
              class="btn"
              @click="
                state.form.system_variables.push({
                  variableId: '',
                  variableValues: [],
                  variableValue: '',
                })
              "
            >
              <el-icon style="margin-right: 4px" size="16">
                <icon_add_outlined></icon_add_outlined>
              </el-icon>
              {{ $t('model.add') }}
            </span>
          </div>
        </template>
        <div v-if="!!state.form.system_variables.length" class="value-list">
          <div class="title">
            <span style="width: calc(48% - 2px)">{{ t('variables.variables') }}</span>
            <span>{{ t('variables.variable_value') }}</span>
          </div>
          <div v-for="(_, index) in state.form.system_variables" :key="index" class="item">
            <el-select
              v-model="state.form.system_variables[index].variableId"
              popper-class="user-light-select-popper"
              style="width: 236px"
              :placeholder="$t('datasource.Please_select')"
            >
              <el-option
                v-for="item in variables"
                :key="item.id"
                :label="item.name"
                :disabled="
                  state.form.system_variables.map((ele: any) => ele.variableId).includes(item.id)
                "
                :value="item.id"
              >
                <div style="width: 100%; display: flex; align-items: center">
                  <el-icon
                    :class="`${variableValueMap[item.id].var_type}-variables`"
                    size="16"
                    style="margin-right: 4px"
                  >
                    <component
                      :is="iconMap[variableValueMap[item.id].var_type as keyof typeof iconMap]"
                    ></component>
                  </el-icon>
                  {{ item.name }}
                </div>
              </el-option>
            </el-select>
            <el-select
              v-if="!state.form.system_variables[index].variableId"
              v-model="state.form.system_variables[index].variableValues"
              multiple
              popper-class="user-light-select-popper"
              style="width: 236px"
              :placeholder="$t('datasource.Please_select')"
            >
              <el-option v-for="item in []" :key="item" :label="item" :value="item"> </el-option>
            </el-select>
            <el-select
              v-else-if="
                variableValueMap[state.form.system_variables[index].variableId].var_type === 'text'
              "
              v-model="state.form.system_variables[index].variableValues"
              multiple
              popper-class="user-light-select-popper"
              style="width: 236px"
              :placeholder="$t('datasource.Please_select')"
            >
              <el-option
                v-for="item in variableValueMap[state.form.system_variables[index].variableId]
                  .value"
                :key="item"
                :label="item"
                :value="item"
              >
              </el-option>
            </el-select>
            <el-input-number
              v-else-if="
                variableValueMap[state.form.system_variables[index].variableId].var_type ===
                'number'
              "
              v-model.number="state.form.system_variables[index].variableValue"
              style="width: 236px"
              :placeholder="$t('variables.please_enter_value')"
              clearable
              max="10000000000000000"
              controls-position="right"
            />
            <el-date-picker
              v-else
              v-model="state.form.system_variables[index].variableValue"
              type="date"
              style="width: 236px"
              value-format="YYYY-MM-DD"
              :placeholder="$t('variables.please_select_date')"
            />
            <el-tooltip
              :offset="14"
              effect="dark"
              :content="$t('dashboard.delete')"
              placement="top"
            >
              <el-icon class="action-btn" size="16" @click="deleteValues(index as number)">
                <IconOpeDelete></IconOpeDelete>
              </el-icon>
            </el-tooltip>
          </div>
        </div>
      </el-form-item>
      <el-form-item :label="$t('user.user_status')">
        <el-switch v-model="state.form.status" :active-value="1" :inactive-value="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button secondary @click="closeForm">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveHandler">
          {{ state.form.id ? $t('common.save') : $t('model.add') }}
        </el-button>
      </div>
    </template>
  </el-drawer>
  <el-dialog
    v-model="dialogVisiblePassword"
    :title="$t('user.change_password')"
    width="500"
    :before-close="handleClosePassword"
  >
    <el-form
      ref="passwordRef"
      :model="password"
      label-width="180px"
      label-position="top"
      :rules="passwordRules"
      class="form-content_error"
      @submit.prevent
    >
      <el-form-item prop="new" :label="t('user.new_password')">
        <el-input
          v-model="password.new"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('user.new_password')
          "
          autocomplete="off"
          clearable
        />
      </el-form-item>
      <el-form-item prop="old" :label="t('user.confirm_password')">
        <el-input
          v-model="password.old"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('user.confirm_password')
          "
          autocomplete="off"
          clearable
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button secondary @click="handleClosePassword">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleConfirmPassword">
          {{ $t('common.save') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
  <UserImport ref="userImportRef" @refresh-grid="search"></UserImport>
  <drawer-main
    ref="drawerMainRef"
    :filter-options="filterOption"
    @trigger-filter="searchCondition"
  />
</template>

<script setup lang="ts">
import { computed, ref, unref, reactive, onMounted, nextTick, shallowRef } from 'vue'
import UserImport from './UserImport.vue'
import SuccessFilled from '@/assets/svg/gou_icon.svg'
import CircleCloseFilled from '@/assets/svg/icon_ban_filled.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import { useI18n } from 'vue-i18n'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { convertFilterText, FilterText } from '@/components/filter-text'
import IconLock from '@/assets/svg/icon-key_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import iconFilter from '@/assets/svg/icon-filter_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import { userApi } from '@/api/user'
import { datasourceApi } from '@/api/datasource'
import { getList as getPermissionList, savePermissions } from '@/api/permissions'
import { decrypted } from '@/views/ds/js/aes'
import field_text from '@/assets/svg/field_text.svg'
import field_time from '@/assets/svg/field_time.svg'
import field_value from '@/assets/svg/field_value.svg'
import { variablesApi } from '@/api/variables'
import { formatTimestamp } from '@/utils/date'
import { ClickOutside as vClickOutside } from 'element-plus-secondary'
import icon_warning_filled from '@/assets/svg/icon_warning_filled.svg'
import { useClipboard } from '@vueuse/core'
import { useUserStore } from '@/stores/user'

const { copy } = useClipboard({ legacy: true })
const userStore = useUserStore()

const { t } = useI18n()
const defaultPwd = ref('Zhishu@123456')
const keyword = ref('')
const dialogFormVisible = ref(false)
const termFormRef = ref()
const checkAll = ref(false)
const dialogVisiblePassword = ref(false)
const isIndeterminate = ref(true)
const drawerMainRef = ref()
const userImportRef = ref()
const selectionLoading = ref(false)

const iconMap = {
  text: field_text,
  number: field_value,
  datetime: field_time,
}
const filterOption = ref<any[]>([
  {
    type: 'enum',
    option: [
      { id: 1, name: t('user.enable') },
      { id: 0, name: t('user.disable') },
    ],
    field: 'status',
    title: t('user.user_status'),
    operate: 'in',
  },
  {
    type: 'enum',
    option: [
      { id: '0', name: t('user.local_creation') },
      { id: '1', name: 'CAS' },
      { id: '2', name: 'OIDC' },
      { id: '3', name: 'LDAP' },
      { id: '4', name: 'OAuth2' },
      /* { id: '5', name: 'SAML2' }, */
      { id: '6', name: t('user.wecom') },
      { id: '7', name: t('user.dingtalk') },
      { id: '8', name: t('user.lark') },
      /* { id: '9', name: t('user.larksuite') }, */
    ],
    field: 'origins',
    title: t('user.user_source'),
    operate: 'in',
  },
])

const defaultForm = {
  id: '',
  name: '',
  account: '',
  email: '',
  status: 1,
  system_role: 'viewer',
  phoneNumber: '',
  project_ids: [],
  project_role_map: {},
  project_permission_map: {},
  system_variables: [],
}
const variables = shallowRef<any[]>([])
const variableValueMap = shallowRef<any>({})
const projectOptions = shallowRef<any[]>([])
const permissionRuleGroups = shallowRef<any[]>([])
const isSuperAdmin = computed(() => userStore.isSystemAdminUser)
const systemRoleOptions = computed(() => [
  { value: 'viewer', label: t('user.system_role_viewer') },
  ...(isSuperAdmin.value
    ? [{ value: 'collab_admin', label: t('user.system_role_collab_admin') }]
    : []),
])
const projectRoleOptions = computed(() => [
  { value: 'viewer', label: t('datasource.project_role_viewer') },
  { value: 'editor', label: t('datasource.project_role_editor') },
])
const state = reactive<any>({
  tableData: [],
  filterTexts: [],
  conditions: [],
  form: { ...defaultForm },
  pageInfo: {
    currentPage: 1,
    pageSize: 20,
    total: 0,
  },
})

const toNumberList = (value: any): number[] => {
  if (!value) return []
  if (Array.isArray(value)) {
    return value.map((item: any) => Number(item)).filter((item: number) => !Number.isNaN(item))
  }
  try {
    const parsed = JSON.parse(value)
    return toNumberList(parsed)
  } catch (e) {
    return []
  }
}

const parseJsonValue = (value: any, fallback: any) => {
  if (!value) return fallback
  if (typeof value === 'object') return value
  try {
    return JSON.parse(value)
  } catch (e) {
    return fallback
  }
}

const normalizeProjectRole = (role: any) => {
  const value = String(role || '').trim().toLowerCase()
  return value === 'editor' ? 'editor' : 'viewer'
}

const buildProjectRoleMap = (projectIds: number[], value: any = {}) => {
  const source = parseJsonValue(value, {})
  const result: any = {}
  projectIds.forEach((id: number) => {
    result[id] = normalizeProjectRole(source?.[id] || source?.[String(id)])
  })
  return result
}

const isHighPrivilegeRole = (role: any) =>
  ['system_admin', 'collab_admin'].includes(String(role || '').trim().toLowerCase())

const canManageUserRole = (row: any) => {
  if (!row) return true
  if (row.system_role === 'system_admin') return false
  return isSuperAdmin.value || !isHighPrivilegeRole(row.system_role)
}

const formatSystemRole = (role: any) => {
  const normalized = String(role || 'viewer').trim().toLowerCase()
  if (normalized === 'collab_admin') return t('user.system_role_collab_admin')
  if (normalized === 'system_admin') return t('user.system_role_system_admin')
  return t('user.system_role_viewer')
}

const systemRoleClass = (role: any) => {
  const normalized = String(role || 'viewer').trim().toLowerCase()
  if (normalized === 'system_admin') return 'is-system-admin'
  if (normalized === 'collab_admin') return 'is-collab-admin'
  return 'is-viewer'
}

const getProjectIdsFromRule = (rule: any): number[] => {
  const ids = (rule.permissions || [])
    .map((item: any) => Number(item.ds_id))
    .filter((item: number) => !Number.isNaN(item))
  return Array.from(new Set<number>(ids))
}

const getPermissionStrategiesByProject = (projectId: any) => {
  const id = Number(projectId)
  return permissionRuleGroups.value.filter((rule: any) => getProjectIdsFromRule(rule).includes(id))
}

const getSelectedStrategiesByProject = (projectId: any) => {
  const id = Number(projectId)
  const selectedIds = toNumberList(state.form.project_permission_map?.[id])
  return getPermissionStrategiesByProject(id).filter((rule: any) =>
    selectedIds.includes(Number(rule.id))
  )
}

const formatRuleGroupSummary = (rule: any, projectId?: any) => {
  const id = Number(projectId)
  const permissions = projectId
    ? (rule.permissions || []).filter((item: any) => Number(item.ds_id) === id)
    : rule.permissions || []
  const rowCount = permissions.filter((item: any) => item.type === 'row').length
  const tableCount = permissions.filter((item: any) => item.type === 'table').length
  const columnCount = permissions.filter((item: any) => item.type === 'column').length
  const parts = []
  if (tableCount) {
    parts.push(t('user.table_rule_count', { msg: tableCount }))
  }
  if (rowCount) {
    parts.push(t('user.row_rule_count', { msg: rowCount }))
  }
  if (columnCount) {
    parts.push(t('user.column_rule_count', { msg: columnCount }))
  }
  return parts.length ? parts.join(' / ') : t('permission.no_rule')
}

const getRuleProjectPermissions = (rule: any, projectId: any) => {
  const id = Number(projectId)
  return (rule.permissions || []).filter((item: any) => Number(item.ds_id) === id)
}

const formatTableAccessSummary = (projectId: any) => {
  const tableNames = new Set<string>()
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    getRuleProjectPermissions(rule, projectId).forEach((permission: any) => {
      if (permission.table_name) {
        tableNames.add(permission.table_name)
      }
    })
  })
  if (!tableNames.size) {
    return t('user.all_project_tables')
  }
  const names = Array.from(tableNames)
  return names.length > 3
    ? t('user.allowed_table_summary_more', { msg: names.slice(0, 3).join('、'), count: names.length - 3 })
    : t('user.allowed_table_summary', { msg: names.join('、') })
}

const formatFieldAccessSummary = (projectId: any) => {
  let restrictedCount = 0
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    getRuleProjectPermissions(rule, projectId).forEach((permission: any) => {
      if (permission.type !== 'column') return
      const list = Array.isArray(permission.permission_list)
        ? permission.permission_list
        : parseJsonValue(permission.permissions, [])
      restrictedCount += (list || []).filter((item: any) => item.enable === false).length
    })
  })
  return restrictedCount
    ? t('user.denied_field_summary', { msg: restrictedCount })
    : t('user.no_field_restriction')
}

const formatRowAccessSummary = (projectId: any) => {
  let rowCount = 0
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    rowCount += getRuleProjectPermissions(rule, projectId).filter((item: any) => item.type === 'row').length
  })
  return rowCount ? t('user.row_filter_summary', { msg: rowCount }) : t('user.no_row_filter')
}

const selectedProjectRows = computed(() => {
  const ids = toNumberList(state.form.project_ids)
  return projectOptions.value.filter((item: any) => ids.includes(Number(item.id)))
})

const formatProjectDatabase = (project: any) => {
  if (!project?.configuration) {
    return project?.type_name || project?.type || '-'
  }
  try {
    const conf = JSON.parse(decrypted(project.configuration) || '{}')
    const database = conf.database || conf.dataBase || conf.filename || project.name
    const schema = conf.dbSchema || conf.schema
    const host = conf.host && conf.port ? `${conf.host}:${conf.port}` : conf.host
    return [database, schema, host].filter(Boolean).join(' / ') || project.name
  } catch (e) {
    return project?.name || '-'
  }
}

const handleProjectIdsChange = (value: any[]) => {
  const ids = toNumberList(value)
  state.form.project_ids = ids
  const nextMap: any = {}
  ids.forEach((id: number) => {
    nextMap[id] = toNumberList(state.form.project_permission_map?.[id])
  })
  state.form.project_permission_map = nextMap
  state.form.project_role_map = buildProjectRoleMap(ids, state.form.project_role_map)
}

const removeProjectAccess = (projectId: any) => {
  const id = Number(projectId)
  state.form.project_ids = toNumberList(state.form.project_ids).filter((item: number) => item !== id)
  const nextMap = { ...(state.form.project_permission_map || {}) }
  delete nextMap[id]
  state.form.project_permission_map = nextMap
  const nextRoleMap = { ...(state.form.project_role_map || {}) }
  delete nextRoleMap[id]
  state.form.project_role_map = nextRoleMap
}

const buildUserProjectPermissionMap = (userId: any, projectIds: number[]) => {
  const result: any = {}
  projectIds.forEach((id: number) => {
    result[id] = []
  })
  if (!userId) return result

  permissionRuleGroups.value.forEach((rule: any) => {
    const users = toNumberList(rule.users || rule.user_list)
    if (!users.includes(Number(userId))) return
    getProjectIdsFromRule(rule).forEach((projectId: number) => {
      if (!projectIds.includes(projectId)) return
      result[projectId] = Array.from(new Set<number>([...(result[projectId] || []), Number(rule.id)]))
    })
  })
  return result
}

const serializePermissionRule = (rule: any, users: number[]) => {
  return {
    id: rule.id,
    name: rule.name,
    permissions: (rule.permissions || []).map((item: any) => ({
      ...item,
      permissions:
        item.type !== 'row'
          ? typeof item.permissions === 'object'
            ? JSON.stringify(item.permissions || [])
            : item.permissions || JSON.stringify(item.permission_list || [])
          : JSON.stringify([]),
      permission_list: [],
      expression_tree:
        item.type === 'row'
          ? typeof item.expression_tree === 'object'
            ? JSON.stringify(item.expression_tree || item.tree || {})
            : item.expression_tree || JSON.stringify(parseJsonValue(item.tree, {}))
          : JSON.stringify({}),
    })),
    users,
  }
}

const syncUserPermissionStrategies = (userId: any): Promise<void> => {
  if (!userId || !permissionRuleGroups.value.length) return Promise.resolve()
  const selectedRuleIds = new Set(
    Object.values(state.form.project_permission_map || {})
      .flatMap((item: any) => toNumberList(item))
      .map((item: number) => Number(item))
  )
  const requests: Promise<any>[] = []

  permissionRuleGroups.value.forEach((rule: any) => {
    if (!getProjectIdsFromRule(rule).length) return
    const currentUsers = toNumberList(rule.users || rule.user_list)
    const shouldInclude = selectedRuleIds.has(Number(rule.id))
    const nextUsers = shouldInclude
      ? Array.from(new Set<number>([...currentUsers, Number(userId)]))
      : currentUsers.filter((item: number) => item !== Number(userId))
    const changed =
      nextUsers.length !== currentUsers.length ||
      nextUsers.some((item: number) => !currentUsers.includes(item))
    if (!changed) return
    rule.users = nextUsers
    requests.push(savePermissions(serializePermissionRule(rule, nextUsers)))
  })

  return Promise.all(requests).then(() => undefined)
}

const rules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.name'),
      trigger: 'blur',
    },
  ],
  account: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.account'),
      trigger: 'blur',
    },
  ],
  email: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.email'),
      trigger: 'blur',
    },
    {
      required: true,
      pattern: /^[a-zA-Z0-9_._-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$/,
      message: t('datasource.incorrect_email_format'),
      trigger: 'blur',
    },
  ],
}

const passwordRules = {
  new: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.new_password'),
      trigger: 'blur',
    },
  ],
  old: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.confirm_password'),
      trigger: 'blur',
    },
  ],
}

const closeResetInfo = (row: any) => {
  row.popoverRef?.hide()
  row.resetInfoShow = false
}
const setPopoverRef = (el: any, row: any) => {
  row.popoverRef = el
}

const copyText = () => {
  copy(defaultPwd.value)
    .then(function () {
      ElMessage.success(t('embedded.copy_successful'))
    })
    .catch(function () {
      ElMessage.error(t('embedded.copy_failed'))
    })
}

const copyPassword = () => {
  copy(defaultPwd.value)
    .then(function () {
      ElMessage.success(t('embedded.copy_successful'))
    })
    .catch(function () {
      ElMessage.error(t('embedded.copy_failed'))
    })
}

const setButtonRef = (el: any, row: any) => {
  row.buttonRef = el
}
const onClickOutside = (row: any) => {
  if (row.popoverRef) {
    unref(row.popoverRef).popperRef?.delayHide?.()
  }
}

const multipleTableRef = ref()
const multipleSelectionAll = ref<any[]>([])
const dialogTitle = ref('')
const passwordRef = ref()
const password = ref({
  new: '',
  old: '',
  id: '',
})

const handleClosePassword = () => {
  dialogVisiblePassword.value = false
}

const deleteValues = (index: number) => {
  state.form.system_variables.splice(index, 1)
}

const handleEditPassword = (row: any) => {
  if (!canManageUserRole(row)) {
    ElMessage.warning(t('user.only_system_admin_manage_admin_roles'))
    return
  }
  userApi.pwd(row.id).then(() => {
    closeResetInfo(row)
    ElMessage({
      type: 'success',
      message: t('common.password_reset_successful'),
    })
  })
}

/* const handleUserImport = () => {
  userImportRef.value.showDialog()
} */

const handleConfirmPassword = () => {
  passwordRef.value.validate((val: any) => {
    if (val) {
      console.info(val)
    }
  })
  dialogVisiblePassword.value = false
}

const handleSelectionChange = (val: any[]) => {
  if (selectionLoading.value) return
  const ids = state.tableData.map((ele: any) => ele.id)
  multipleSelectionAll.value = [
    ...multipleSelectionAll.value.filter((ele) => !ids.includes(ele.id)),
    ...val,
  ]
  isIndeterminate.value = !(val.length === 0 || val.length === state.tableData.length)
  checkAll.value = val.length === state.tableData.length
}
const handleCheckAllChange = (val: any) => {
  isIndeterminate.value = false
  handleSelectionChange(val ? state.tableData : [])
  if (val) {
    handleToggleRowSelection()
  } else {
    multipleTableRef.value.clearSelection()
  }
}

const handleToggleRowSelection = (check: boolean = true) => {
  let i = 0
  const ids = multipleSelectionAll.value.map((ele: any) => ele.id)
  for (const key in state.tableData) {
    if (ids.includes((state.tableData[key] as any).id)) {
      i += 1
      multipleTableRef.value.toggleRowSelection(state.tableData[key], check)
    }
  }
  checkAll.value = i === state.tableData.length
  isIndeterminate.value = !(i === 0 || i === state.tableData.length)
  selectionLoading.value = false
}
const handleSearch = ($event: any = {}) => {
  if ($event?.isComposing) {
    return
  }
  state.pageInfo.currentPage = 1
  search()
}
const fillFilterText = () => {
  const textArray = state.conditions?.length
    ? convertFilterText(state.conditions, filterOption.value)
    : []
  state.filterTexts = [...textArray]
  Object.assign(state.filterTexts, textArray)
}
const clearFilter = (params?: number) => {
  let index = params ? params : 0
  if (isNaN(index)) {
    state.filterTexts = []
  } else {
    state.filterTexts.splice(index, 1)
  }
  drawerMainRef.value.clearFilter(index)
}
const searchCondition = (conditions: any) => {
  state.conditions = conditions
  fillFilterText()
  handleCurrentChange(1)

  drawerMainClose()
}
const drawerMainOpen = async () => {
  drawerMainRef.value.init()
}
const drawerMainClose = () => {
  drawerMainRef.value.close()
}
const editHandler = (row: any) => {
  if (row && !canManageUserRole(row)) {
    ElMessage.warning(t('user.only_system_admin_manage_admin_roles'))
    return
  }
  Promise.all([variablesApi.listAll(), datasourceApi.list(), getPermissionList()])
    .then(([variableRes, projectRes, permissionRes]: any[]) => {
      projectOptions.value = projectRes || []
      permissionRuleGroups.value = permissionRes || []
      variables.value = variableRes.filter((ele: any) => ele.type === 'custom')
      variableValueMap.value = variables.value.reduce((pre, next) => {
        pre[next.id] = {
          value: next.value,
          var_type: next.var_type,
          name: next.name,
        }
        return pre
      }, {})

      if (row) {
        const projectIds = (row.project_ids || []).map((id: any) => Number(id))
        state.form = {
          ...row,
          system_role: row.system_role || 'viewer',
          project_ids: projectIds,
          project_role_map: buildProjectRoleMap(projectIds, row.project_role_map),
          project_permission_map: buildUserProjectPermissionMap(row.id, projectIds),
          system_variables: (row.system_variables || []).map((ele: any) => ({
            ...ele,
            variableValue: ele.variableValues[0],
          })),
        }
      } else {
        state.form = {
          ...defaultForm,
          system_role: 'viewer',
          project_ids: [],
          project_role_map: {},
          project_permission_map: {},
          system_variables: [],
        }
      }
    })
    .finally(() => {
      state.form.system_variables = state.form.system_variables.filter((ele: any) => {
        if (variableValueMap.value[ele.variableId]) {
          if (variableValueMap.value[ele.variableId].var_type === 'text') {
            ele.variableValues = variableValueMap.value[ele.variableId].value.filter(
              (item: any) => ele.variableValues.indexOf(item) > -1
            )
            return !!ele.variableValues.length
          }
          return true
        }
        return false
      })
      dialogTitle.value = row?.id ? t('user.edit_user') : t('user.add_users')
      dialogFormVisible.value = true
    })
}

const statusHandler = (row: any) => {
  if (!canManageUserRole(row)) {
    row.status = row.status ? 0 : 1
    ElMessage.warning(t('user.only_system_admin_manage_admin_roles'))
    return
  }
  /* state.form = { ...row }
  editTerm() */
  const param = {
    id: row.id,
    status: row.status,
  }
  userApi.status(param)
}

const cancelDelete = () => {
  handleToggleRowSelection(false)
  multipleSelectionAll.value = []
  checkAll.value = false
  isIndeterminate.value = false
}
const deleteBatchUser = () => {
  const protectedUsers = multipleSelectionAll.value.filter((ele) => !canManageUserRole(ele))
  if (protectedUsers.length) {
    ElMessage.warning(t('user.only_system_admin_manage_admin_roles'))
    return
  }
  ElMessageBox.confirm(t('user.selected_2_users', { msg: multipleSelectionAll.value.length }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    userApi.deleteBatch(multipleSelectionAll.value.map((ele) => ele.id)).then(() => {
      multipleSelectionAll.value = []
      ElMessage({
        type: 'success',
        message: t('dashboard.delete_success'),
      })
      handleCurrentChange(1)
    })
  })
}
const deleteHandler = (row: any) => {
  if (!canManageUserRole(row)) {
    ElMessage.warning(t('user.only_system_admin_manage_admin_roles'))
    return
  }
  ElMessageBox.confirm(t('user.del_user', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    userApi.delete(row.id).then(() => {
      multipleSelectionAll.value = multipleSelectionAll.value.filter((ele) => ele.id !== row.id)
      ElMessage({
        type: 'success',
        message: t('dashboard.delete_success'),
      })
      handleCurrentChange(1)
    })
  })
}

const closeForm = () => {
  dialogFormVisible.value = false
}
const onFormClose = () => {
  state.form = {
    ...defaultForm,
    system_role: 'viewer',
    project_ids: [],
    project_role_map: {},
    project_permission_map: {},
    system_variables: [],
  }
  dialogFormVisible.value = false
}

const configParams = () => {
  let str = ''
  if (keyword.value) {
    str += `keyword=${keyword.value}`
  }

  state.conditions.forEach((ele: any) => {
    if (ele.field === 'status' && ele.value.length === 2) {
      return
    }
    ele.value.forEach((itx: any) => {
      str += str ? `&${ele.field}=${itx}` : `${ele.field}=${itx}`
    })
  })

  if (str.length) {
    str = `?${str}`
  }

  return str
}

const search = () => {
  userApi
    .pager(configParams(), state.pageInfo.currentPage, state.pageInfo.pageSize)
    .then((res: any) => {
      state.tableData = res.items
      state.pageInfo.total = res.total
      selectionLoading.value = true
      nextTick(() => {
        handleToggleRowSelection()
      })
    })
}

const formatVariableValues = () => {
  if (!state.form.system_variables?.length) return []
  return state.form.system_variables.map((ele: any) => ({
    variableId: ele.variableId,
    variableValues: ['number', 'datetime'].includes(variableValueMap.value[ele.variableId].var_type)
      ? [ele.variableValue]
      : ele.variableValues,
  }))
}

const addTerm = () => {
  const { account, email, name, status, system_role, project_ids, project_role_map } = state.form
  userApi
    .add({
      account,
      email,
      name,
      status,
      system_role,
      project_ids,
      project_role_map: buildProjectRoleMap(toNumberList(project_ids), project_role_map),
      system_variables: formatVariableValues(),
    })
    .then((res: any) => syncUserPermissionStrategies(res?.id).then(() => res))
    .then(() => {
      onFormClose()
      handleCurrentChange(1)

      ElMessage({
        type: 'success',
        message: t('common.save_success'),
      })
    })
}
const editTerm = () => {
  const {
    account,
    id,
    create_time,
    email,
    language,
    name,
    project_ids,
    project_role_map,
    origin,
    status,
    system_role,
  } =
    state.form
  userApi
    .edit({
      account,
      id,
      create_time,
      email,
      language,
      name,
      project_ids,
      project_role_map: buildProjectRoleMap(toNumberList(project_ids), project_role_map),
      origin,
      status,
      system_role,
      system_variables: formatVariableValues(),
    })
    .then(() => syncUserPermissionStrategies(id))
    .then(() => {
      onFormClose()
      handleCurrentChange(1)

      ElMessage({
        type: 'success',
        message: t('common.save_success'),
      })
    })
}

const duplicateName = () => {
  if (state.form.id) {
    editTerm()
  } else {
    addTerm()
  }
}

const validateSystemVariables = () => {
  const { system_variables = [] } = state.form
  if (system_variables?.length) {
    return system_variables.some((ele: any) => {
      const obj = variableValueMap.value[ele.variableId]
      if (obj.var_type === 'text' && !ele.variableValues.length) {
        ElMessage.error(t('variables.​​cannot_be_empty'))
        return true
      }

      if (obj.var_type === 'number' && [null, undefined, ''].includes(ele.variableValue)) {
        ElMessage.error(t('variables.​​cannot_be_empty'))
        return true
      }

      if (obj.var_type === 'number') {
        const [min, max] = obj.value
        if (ele.variableValue > max || ele.variableValue < min) {
          ElMessage.error(t('variables.1_to_100', { name: obj.name, min, max }))
          return true
        }
      }

      if (obj.var_type === 'datetime') {
        const [min, max] = obj.value
        if (
          +new Date(ele.variableValue) > +new Date(max) ||
          +new Date(ele.variableValue) < +new Date(min)
        ) {
          ElMessage.error(
            t('variables.1_to_100_de', {
              name: obj.name,
              min,
              max,
            })
          )
          return true
        }
      }
    })
  }

  return false
}

const saveHandler = () => {
  termFormRef.value.validate((res: any) => {
    if (res) {
      if (validateSystemVariables()) return
      duplicateName()
    }
  })
}
const handleSizeChange = (val: number) => {
  state.pageInfo.pageSize = val
  state.pageInfo.currentPage = 1
  search()
}
const handleCurrentChange = (val: number) => {
  state.pageInfo.currentPage = val
  search()
}
const loadDefaultPwd = () => {
  userApi.defaultPwd().then((res) => {
    if (res) {
      defaultPwd.value = res
    }
  })
}
const formatUserOrigin = (origin?: number) => {
  if (!origin) {
    return t('user.local_creation')
  }
  const originArray = [
    'CAS',
    'OIDC',
    'LDAP',
    'OAuth2',
    'SAML2',
    t('user.wecom'),
    t('user.dingtalk'),
    t('user.lark'),
    t('user.larksuite'),
  ]
  return originArray[origin - 1]
}

onMounted(() => {
  handleCurrentChange(1)

  loadDefaultPwd()
})
</script>

<style lang="less" scoped>
.zhishu-table-container {
  width: 100%;
  height: 100%;
  position: relative;
  .bottom-select {
    position: absolute;
    height: 64px;
    width: calc(100% + 48px);
    left: -24px;
    background-color: #fff;
    bottom: -16px;
    border-top: 1px solid #1f232926;
    display: flex;
    align-items: center;
    padding-left: 24px;
    z-index: 10;

    .danger-button {
      border: 1px solid var(--ed-color-danger);
      color: var(--ed-color-danger);
      border-radius: var(--ed-border-radius-base);
      min-width: 80px;
      height: 32px;
      line-height: 32px;
      text-align: center;
      cursor: pointer;
      margin: 0 16px;
      background-color: transparent;
    }

    .selected {
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      color: #646a73;
      margin-right: 12px;
    }
  }
  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    .page-title {
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }
  }
  .zhishu-table_user {
    width: 100%;
    max-height: calc(100vh - 150px);
    overflow-y: auto;

    &.show-pagination_height {
      max-height: calc(100vh - 215px);
    }

    :deep(.ed-popper.is-dark) {
      max-width: 400px;
    }
    :deep(.ed-table) {
      --el-table-header-bg-color: #f5f7fa;
      --el-table-border-color: #ebeef5;
      --el-table-header-text-color: #606266;

      th {
        font-weight: 600;
        height: 48px;
      }

      td {
        height: 52px;
      }
    }
    .table-operate {
      display: flex;
      align-items: center;
      height: 24px;
      line-height: 24px;
      .ed-icon + .ed-icon {
        margin-left: 12px;
      }

      .line {
        margin: 0 10px 0 12px;
        height: 16px;
        width: 1px;
        background-color: #1f232926;
      }

      .ed-icon {
        position: relative;
        cursor: pointer;
        color: #646a73;

        &.disabled {
          cursor: not-allowed;
          color: #b8bdc6;

          &::after {
            display: none !important;
          }
        }

        &::after {
          content: '';
          background-color: #1f23291a;
          position: absolute;
          border-radius: 6px;
          width: 24px;
          height: 24px;
          transform: translate(-50%, -50%);
          top: 50%;
          left: 50%;
          display: none;
        }

        &:hover {
          &::after {
            display: block;
          }
        }
      }
    }

    .system-role-text {
      font-size: 14px;
      font-weight: 500;
      line-height: 22px;

      &.is-viewer {
        color: #646a73;
        font-weight: 400;
      }

      &.is-collab-admin {
        color: #245bdb;
      }

      &.is-system-admin {
        color: #c42a2a;
      }
    }
  }

  .pagination-container {
    display: flex;
    justify-content: end;
    align-items: center;
    margin-top: 16px;
  }
}

.user-status-container {
  display: flex;
  align-items: center;
  font-weight: 400;
  font-size: 14px;
  line-height: 22px;

  .ed-icon {
    margin-right: 8px;
  }
}
</style>

<style lang="less">
.reset-pwd-confirm {
  padding: 5px 15px;
  .confirm-header {
    width: 100%;
    min-height: 40px;
    line-height: 40px;
    display: flex;
    flex-direction: row;
    .icon-span {
      color: var(--ed-color-warning);
      font-size: 22px;
      i {
        top: 3px;
      }
    }
    .header-span {
      font-size: 16px;
      font-weight: bold;
      margin-left: 10px;
      white-space: pre-wrap;
      word-break: keep-all;
    }
  }
  .confirm-foot {
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: center;
    margin-top: 15px;
    .ed-button {
      min-width: 48px;
      height: 28px;
      line-height: 28px;
      font-size: 12px;
    }
  }
  .confirm-warning {
    font-size: 12px;
    color: var(--ed-color-danger);
    margin-left: 33px;
  }
  .confirm-content {
    margin-left: 33px;
    display: flex;
    align-items: center;
  }
}
.user-add-class {
  .ed-drawer,
  .ed-drawer__header,
  .ed-drawer__body,
  .ed-drawer__footer {
    background: #fff !important;
    color: #1f2329 !important;
  }

  .ed-drawer__header {
    border-bottom: 1px solid #dee0e3;
    margin-bottom: 0;
    padding-bottom: 16px;
  }

  .ed-drawer__body {
    padding-top: 16px;
  }

  .ed-drawer__footer {
    border-top: 1px solid #dee0e3;
  }

  .ed-form-item__label,
  .ed-radio,
  .ed-checkbox,
  .ed-switch__label,
  .value-list,
  .project-permission-panel {
    color: #1f2329 !important;
  }

  .ed-input__wrapper,
  .ed-select__wrapper,
  .ed-textarea__inner,
  .ed-input-number,
  .ed-date-editor {
    background-color: #fff !important;
    border-color: #d0d3d6 !important;
    box-shadow: 0 0 0 1px #d0d3d6 inset !important;
    color: #1f2329 !important;
  }

  .ed-input__inner,
  .ed-select__placeholder,
  .ed-select__selected-item,
  .ed-textarea__inner {
    color: #1f2329 !important;
  }

  .ed-input__inner::placeholder,
  .ed-textarea__inner::placeholder {
    color: #8f959e !important;
  }

  .ed-input.is-disabled .ed-input__wrapper,
  .ed-select.is-disabled .ed-select__wrapper {
    background-color: #f5f6f7 !important;
    box-shadow: 0 0 0 1px #dee0e3 inset !important;
  }

  .ed-input.is-disabled .ed-input__inner,
  .ed-select.is-disabled .ed-select__selected-item {
    color: #8f959e !important;
    -webkit-text-fill-color: #8f959e !important;
  }

  .ed-button.is-secondary {
    background-color: #fff !important;
    border-color: #d0d3d6 !important;
    color: #1f2329 !important;
  }

  .ed-button.is-text {
    color: #336df4 !important;
  }

  .ed-table,
  .ed-table__body-wrapper,
  .ed-table__inner-wrapper,
  .ed-table tr,
  .ed-table td.ed-table__cell {
    background-color: #fff !important;
    color: #1f2329 !important;
    border-color: #dee0e3 !important;
  }

  .ed-table__header-wrapper,
  .ed-table th.ed-table__cell {
    background-color: #f5f6f7 !important;
    color: #1f2329 !important;
    border-color: #dee0e3 !important;
  }

  .ed-table--enable-row-hover .ed-table__body tr:hover > td.ed-table__cell {
    background-color: #f5f6f7 !important;
  }

  .ed-form-item__label:has(.btn) {
    padding-right: 0;
    width: 100%;
    margin-bottom: 8px;
  }
  .project-permission-panel {
    width: 100%;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    overflow: hidden;
    background: #fff;

    .project-permission-toolbar {
      min-height: 48px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #dee0e3;
      background: #f8f9fa;
    }

    .project-permission-count {
      color: #646a73;
      font-size: 13px;
      white-space: nowrap;
    }

    .project-permission-table {
      .ed-table__cell {
        vertical-align: top;
      }
    }

    .project-cell {
      min-width: 0;
    }

    .project-name {
      font-weight: 500;
      color: #1f2329;
      line-height: 22px;
    }

    .project-type,
    .database-label,
    .muted {
      color: #8f959e;
      font-size: 12px;
      line-height: 20px;
    }

    .database-label {
      display: inline-block;
      max-width: 150px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .permission-summary {
      min-height: 24px;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    .summary-line {
      max-width: 100%;
      color: #646a73;
      font-size: 12px;
      line-height: 18px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .more-strategy {
      color: #646a73;
      font-size: 12px;
    }
  }

  .permission-option {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;

    .permission-option-name {
      max-width: 150px;
    }

    .permission-option-summary {
      color: #8f959e;
      font-size: 12px;
      white-space: nowrap;
    }
  }

  .value-list {
    width: 100%;
    padding: 16px;
    border-radius: 6px;
    background-color: #f5f6f7;
    .title {
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      margin-bottom: 8px;
      display: flex;
    }
    .item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;

      &:not(:last-child) {
        margin-bottom: 8px;
      }

      .action-btn {
        width: 24px;
        height: 24px;
        border-radius: 6px;
        cursor: pointer;
        color: #646a73;

        &:hover {
          background-color: #1f23291a;
        }
      }
    }
  }
  .btn {
    margin-left: auto;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
    border-radius: 6px;
    margin-right: -4px;
    cursor: pointer;

    &:hover {
      background-color: #1f23291a;
    }
  }
  .down-template {
    display: flex;
    width: 100%;
    height: 40px;
    align-items: center;
    line-height: 40px;
    background: var(--ed-color-primary-80, #d2f1e9);
    border-radius: 6px;
    padding-left: 10px;
    .icon-span {
      color: var(--ed-color-primary);
      font-size: 18px;
      i {
        top: 3px;
      }
    }
    .down-template-content {
      font-size: 14px;
      display: flex;
      flex-direction: row;
      margin-left: 10px;
      .down-button {
        height: 40px;
      }
    }
  }
}

:root[data-theme='dark'] {
  .user-add-class {
    color-scheme: light;

    .ed-drawer,
    .ed-drawer__header,
    .ed-drawer__body,
    .ed-drawer__footer,
    .ed-form,
    .project-permission-panel,
    .project-permission-toolbar,
    .value-list {
      background-color: #fff !important;
      color: #1f2329 !important;
      border-color: #dee0e3 !important;
    }

    .ed-drawer__title,
    .ed-form-item__label,
    .ed-radio,
    .ed-checkbox,
    .ed-switch__label,
    .value-list .title,
    .value-list .item,
    .project-name,
    .ed-table,
    .ed-table .cell,
    .ed-table__empty-text {
      color: #1f2329 !important;
    }

    .project-type,
    .database-label,
    .muted,
    .summary-line,
    .more-strategy,
    .project-permission-count,
    .permission-option-summary {
      color: #646a73 !important;
    }

    .ed-input .ed-input__wrapper,
    .ed-select .ed-select__wrapper,
    .ed-textarea .ed-textarea__inner,
    .ed-input-number,
    .ed-date-editor {
      background-color: #fff !important;
      border-color: #d0d3d6 !important;
      box-shadow: 0 0 0 1px #d0d3d6 inset !important;
      color: #1f2329 !important;
    }

    .ed-input .ed-input__inner,
    .ed-select .ed-select__placeholder,
    .ed-select .ed-select__selected-item,
    .ed-textarea .ed-textarea__inner,
    .ed-input-number .ed-input__inner {
      color: #1f2329 !important;
      -webkit-text-fill-color: #1f2329 !important;
    }

    .ed-input .ed-input__inner::placeholder,
    .ed-textarea .ed-textarea__inner::placeholder,
    .ed-select .ed-select__placeholder {
      color: #8f959e !important;
      -webkit-text-fill-color: #8f959e !important;
    }

    .ed-input.is-disabled .ed-input__wrapper,
    .ed-select.is-disabled .ed-select__wrapper {
      background-color: #f5f6f7 !important;
      box-shadow: 0 0 0 1px #dee0e3 inset !important;
    }

    .ed-input.is-disabled .ed-input__inner,
    .ed-select.is-disabled .ed-select__placeholder,
    .ed-select.is-disabled .ed-select__selected-item {
      color: #8f959e !important;
      -webkit-text-fill-color: #8f959e !important;
    }

    .ed-table,
    .ed-table__header-wrapper,
    .ed-table__body-wrapper,
    .ed-table__inner-wrapper,
    .ed-table__empty-block,
    .ed-table tr,
    .ed-table td.ed-table__cell {
      background-color: #fff !important;
      color: #1f2329 !important;
      border-color: #dee0e3 !important;
    }

    .ed-table th.ed-table__cell,
    .ed-table__header th,
    .ed-table__header tr {
      background-color: #f5f6f7 !important;
      color: #1f2329 !important;
      border-color: #dee0e3 !important;
    }

    .ed-table--enable-row-hover .ed-table__body tr:hover > td.ed-table__cell {
      background-color: #f5f6f7 !important;
      color: #1f2329 !important;
    }

    .ed-button.is-secondary,
    .dialog-footer .ed-button:not(.ed-button--primary) {
      background-color: #fff !important;
      border-color: #d0d3d6 !important;
      color: #646a73 !important;
    }

    .ed-button.is-text {
      background-color: transparent !important;
      color: #336df4 !important;
    }
  }

  .user-light-select-popper,
  .user-light-select-popper.ed-popper,
  .user-light-select-popper .ed-select-dropdown,
  .user-light-select-popper .ed-scrollbar,
  .user-light-select-popper .ed-scrollbar__wrap,
  .user-light-select-popper .ed-scrollbar__view {
    color-scheme: light;
    background-color: #fff !important;
    color: #1f2329 !important;
    border-color: #dee0e3 !important;
  }

  .user-light-select-popper .ed-select-dropdown__item {
    background-color: #fff !important;
    color: #1f2329 !important;
  }

  .user-light-select-popper .ed-select-dropdown__item.hover,
  .user-light-select-popper .ed-select-dropdown__item:hover {
    background-color: #f5f6f7 !important;
    color: #1f2329 !important;
  }

  .user-light-select-popper .ed-select-dropdown__item.selected {
    color: #336df4 !important;
    background-color: #eef3ff !important;
  }

  .user-light-select-popper .ed-select-dropdown__item.is-disabled {
    color: #b8bdc6 !important;
    background-color: #fff !important;
  }

  .user-light-select-popper .ed-popper__arrow::before {
    background-color: #fff !important;
    border-color: #dee0e3 !important;
  }
}
</style>
