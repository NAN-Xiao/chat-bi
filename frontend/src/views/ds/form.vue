<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="600"
    :destroy-on-close="true"
    :close-on-click-modal="false"
    @closed="close"
    modal-class="add-datasource_dialog"
  >
    <template #header="">
      <div style="display: flex">
        <div style="margin-right: 24px">{{ dialogTitle }}</div>
        <el-steps
          v-show="isCreate"
          :active="active"
          align-center
          custom
          style="max-width: 400px; flex: 1"
        >
          <el-step title="Base Info" />
          <el-step title="Choose Tables" />
        </el-steps>
      </div>
    </template>

    <div v-show="active === 0" class="container">
      <el-form
        :model="form"
        label-position="top"
        label-width="auto"
        ref="dsFormRef"
        :rules="rules"
      >
        <el-form-item label="Name" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" :rows="2" type="textarea" />
        </el-form-item>
        <el-form-item label="Type">
          <el-select
            v-model="form.type"
            placeholder="Select Type"
            :disabled="!isCreate"
          >
            <el-option
              v-for="item in dsType"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <div v-if="form.type === 'excel'">
          <el-form-item label="File">
            <el-upload
              :disabled="!isCreate"
              accept=".xls, .xlsx, .csv"
              :headers="headers"
              action="http://localhost:8000/api/v1/datasource/uploadExcel"
              :before-upload="beforeUpload"
              :on-success="onSuccess"
            >
              <el-button>Upload</el-button>
              <template #tip>
                <div class="el-upload__tip">
                  Only support .xls, .xlsx, .csv, size less than 50MB.
                </div>
              </template>
            </el-upload>
          </el-form-item>
        </div>
        <div v-else>
          <el-form-item label="Host/Ip">
            <el-input v-model="config.host" />
          </el-form-item>
          <el-form-item label="Port">
            <el-input v-model="config.port" />
          </el-form-item>
          <el-form-item label="Username">
            <el-input v-model="config.username" />
          </el-form-item>
          <el-form-item label="Password">
            <el-input v-model="config.password" type="password" show-password />
          </el-form-item>
          <el-form-item label="Database">
            <el-input v-model="config.database" />
          </el-form-item>
          <el-form-item label="Connect Mode" v-if="form.type === 'oracle'">
            <el-radio-group v-model="config.mode">
              <el-radio value="service_name">Service Name</el-radio>
              <el-radio value="sid">SID</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="Extra JDBC String">
            <el-input v-model="config.extraJdbc" />
          </el-form-item>
          <el-form-item label="Schema" v-if="haveSchema.includes(form.type)">
            <el-input v-model="config.dbSchema" />
            <el-button link type="primary" :icon="Plus" v-if="false"
              >Get Schema</el-button
            >
          </el-form-item>
          <span v-if="form.type === 'sqlServer'">Supported version: 2012+</span>
          <span v-else-if="form.type === 'oracle'">Supported version: 12+</span>
          <span v-else-if="form.type === 'mysql'">Supported version: 5.6+</span>
          <span v-else-if="form.type === 'pg'">Supported version: 9.6+</span>
        </div>
      </el-form>
    </div>
    <div v-show="active === 1" class="container" v-loading="tableListLoading">
      <el-checkbox-group v-model="checkList" style="position: relative">
        <FixedSizeList
          :itemSize="40"
          :data="tableList"
          :total="tableList.length"
          :width="560"
          :height="400"
          :scrollbarAlwaysOn="true"
          class-name="ed-select-dropdown__list"
          layout="vertical"
        >
          <template #default="{ index, style }">
            <div class="list-item_primary" :style="style">
              <el-checkbox :label="tableList[index].tableName">{{
                tableList[index].tableName
              }}</el-checkbox>
            </div>
          </template>
        </FixedSizeList>
      </el-checkbox-group>
      <span>Selected: {{ checkList.length }}/{{ tableList.length }}</span>
    </div>
    <div style="display: flex; justify-content: flex-end; margin-top: 20px">
      <el-button @click="close">Cancel</el-button>
      <el-button
        v-show="!isCreate && !isEditTable && form.type !== 'excel'"
        @click="check"
        >Test Connect</el-button
      >
      <el-button
        v-show="active === 0 && isCreate"
        type="primary"
        @click="next(dsFormRef)"
        >Next</el-button
      >
      <el-button v-show="active === 1 && isCreate" @click="preview"
        >Preview</el-button
      >
      <el-button
        v-show="active === 1 || !isCreate"
        type="primary"
        @click="save(dsFormRef)"
        >Save</el-button
      >
    </div>
  </el-dialog>
</template>
<script lang="ts" setup>
import { ref, reactive } from "vue";
import { datasourceApi } from "@/api/datasource";
import { encrypted, decrypted } from "./js/aes";
import { ElMessage } from "element-plus-secondary";
import type { FormInstance, FormRules } from "element-plus-secondary";
import FixedSizeList from "element-plus-secondary/es/components/virtual-list/src/components/fixed-size-list.mjs";
import { Plus } from "@element-plus/icons-vue";
import { useCache } from "@/utils/useCache";
import { dsType, haveSchema } from "@/views/ds/js/ds-type";

const { wsCache } = useCache();
const dsFormRef = ref<FormInstance>();
const emit = defineEmits(["refresh"]);
const active = ref(0);
const isCreate = ref(true);
const isEditTable = ref(false);
const checkList = ref<any>([]);
const tableList = ref<any>([]);
const excelUploadSuccess = ref(false);
const tableListLoading = ref(false);
const token = wsCache.get("user.token");
const headers = ref<any>({ "X-SQLBOT-TOKEN": `Bearer ${token}` });
const dialogTitle = ref("");

const rules = reactive<FormRules>({
  name: [
    { required: true, message: "Please input name", trigger: "blur" },
    { min: 1, max: 50, message: "Length should be 1 to 50", trigger: "blur" },
  ],
});

const dialogVisible = ref<boolean>(false);
const form = ref<any>({
  name: "",
  description: "",
  type: "mysql",
  configuration: "",
});
const config = ref<any>({
  driver: "",
  host: "",
  port: 0,
  username: "",
  password: "",
  database: "",
  extraJdbc: "",
  dbSchema: "",
  filename: "",
  sheets: [],
  mode: "service_name",
});

const close = () => {
  dialogVisible.value = false;
  isCreate.value = true;
  active.value = 0;
  isEditTable.value = false;
  checkList.value = [];
  tableList.value = [];
  excelUploadSuccess.value = false;
};

const open = (item: any, editTable: boolean = false) => {
  isEditTable.value = false;
  if (item) {
    dialogTitle.value = "Edit Datasource";
    isCreate.value = false;
    form.value.id = item.id;
    form.value.name = item.name;
    form.value.description = item.description;
    form.value.type = item.type;
    form.value.configuration = item.configuration;
    if (item.configuration) {
      const configuration = JSON.parse(decrypted(item.configuration));
      config.value.host = configuration.host;
      config.value.port = configuration.port;
      config.value.username = configuration.username;
      config.value.password = configuration.password;
      config.value.database = configuration.database;
      config.value.extraJdbc = configuration.extraJdbc;
      config.value.dbSchema = configuration.dbSchema;
      config.value.filename = configuration.filename;
      config.value.sheets = configuration.sheets;
      config.value.mode = configuration.mode;
    }

    if (editTable) {
      dialogTitle.value = "Choose Tables";
      active.value = 1;
      isEditTable.value = true;
      isCreate.value = false;
      // request tables and check tables

      datasourceApi.tableList(item.id).then((res) => {
        checkList.value = res.map((ele: any) => {
          return ele.table_name;
        });
        if (item.type === "excel") {
          tableList.value = config.value.sheets;
        } else {
          tableListLoading.value = true;
          datasourceApi
            .getTablesByConf(form.value)
            .then((table) => {
              tableList.value = table;
              checkList.value = checkList.value.filter((ele: string) => {
                return table
                  .map((ele: any) => {
                    return ele.tableName;
                  })
                  .includes(ele);
              });
            })
            .finally(() => {
              tableListLoading.value = false;
            });
        }
      });
    }
  } else {
    dialogTitle.value = "Add Datasource";
    isCreate.value = true;
    isEditTable.value = false;
    checkList.value = [];
    tableList.value = [];
    form.value = {
      name: "",
      description: "",
      type: "mysql",
      configuration: "",
    };
    config.value = {
      driver: "",
      host: "",
      port: 0,
      username: "",
      password: "",
      database: "",
      extraJdbc: "",
      dbSchema: "",
      filename: "",
      sheets: [],
      mode: "service_name",
    };
  }
  dialogVisible.value = true;
};

const save = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate((valid) => {
    if (valid) {
      const list = tableList.value
        .filter((ele: any) => {
          return checkList.value.includes(ele.tableName);
        })
        .map((ele: any) => {
          return { table_name: ele.tableName, table_comment: ele.tableComment };
        });

      buildConf();
      if (form.value.id) {
        if (!isEditTable.value) {
          // only update datasource config info
          datasourceApi.update(form.value).then((res) => {
            console.log(res);
            close();
            emit("refresh");
          });
        } else {
          // save table and field
          datasourceApi.chooseTables(form.value.id, list).then(() => {
            close();
          });
        }
      } else {
        form.value.tables = list;
        datasourceApi.add(form.value).then((res: any) => {
          console.log(res);
          close();
          emit("refresh");
        });
      }
    }
  });
};

const buildConf = () => {
  form.value.configuration = encrypted(
    JSON.stringify({
      host: config.value.host,
      port: config.value.port,
      username: config.value.username,
      password: config.value.password,
      database: config.value.database,
      extraJdbc: config.value.extraJdbc,
      dbSchema: config.value.dbSchema,
      filename: config.value.filename,
      sheets: config.value.sheets,
      mode: config.value.mode,
    })
  );
};

const check = () => {
  buildConf();
  datasourceApi.check(form.value).then((res: any) => {
    if (res) {
      ElMessage({
        message: "Connect success",
        type: "success",
        showClose: true,
      });
    } else {
      ElMessage({
        message: "Connect failed",
        type: "error",
        showClose: true,
      });
    }
  });
};

const next = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate((valid) => {
    if (valid) {
      if (form.value.type === "excel") {
        // next, show tables
        if (excelUploadSuccess.value) {
          active.value++;
        }
      } else {
        // check status if success do next
        buildConf();
        datasourceApi.check(form.value).then((res: boolean) => {
          if (res) {
            active.value++;
            // request tables
            datasourceApi.getTablesByConf(form.value).then((res) => {
              tableList.value = res;
            });
          } else {
            ElMessage({
              message: "Connect failed",
              type: "error",
              showClose: true,
            });
          }
        });
      }
    }
  });
};

const preview = () => {
  active.value--;
};

const beforeUpload = (rawFile: any) => {
  if (rawFile.size / 1024 / 1024 > 50) {
    ElMessage.error("File size can not exceed 50MB!");
    return false;
  }
  return true;
};

const onSuccess = (response: any) => {
  config.value.filename = response.data.filename;
  config.value.sheets = response.data.sheets;
  tableList.value = response.data.sheets;
  excelUploadSuccess.value = true;
};

defineExpose({ open });
</script>
<style lang="less">
.add-datasource_dialog {
  .container {
    max-height: 600px;
    overflow-y: auto;
    .ed-vl__window.ed-select-dropdown__list::-webkit-scrollbar {
      width: 0;
      height: 0;
    }
  }
}
</style>
