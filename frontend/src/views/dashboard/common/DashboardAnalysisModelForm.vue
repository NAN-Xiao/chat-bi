<script setup lang="ts">
import { CopyDocument, Delete, EditPen, Filter, FolderOpened, InfoFilled, MoreFilled, Plus, Setting } from '@element-plus/icons-vue'
import BuilderSectionIcon from '@/assets/svg/dv-view.svg'
import AttributionWindowPicker from '@/views/dashboard/common/AttributionWindowPicker.vue'
import BuilderFieldPicker from '@/views/dashboard/common/BuilderFieldPicker.vue'
import BuilderFilterTree from '@/views/dashboard/common/BuilderFilterTree.vue'
import DistributionIntervalSettings from '@/views/dashboard/common/DistributionIntervalSettings.vue'
import DistributionMetricPicker from '@/views/dashboard/common/DistributionMetricPicker.vue'
import FunnelWindowPicker from '@/views/dashboard/common/FunnelWindowPicker.vue'
import IntervalLimitPicker from '@/views/dashboard/common/IntervalLimitPicker.vue'
import PathEventList from '@/views/dashboard/common/PathEventList.vue'
import PathSessionGapPicker from '@/views/dashboard/common/PathSessionGapPicker.vue'
import RevenueMetricPicker from '@/views/dashboard/common/RevenueMetricPicker.vue'
import {
  PATH_EVENT_LIMIT,
} from '@/views/dashboard/common/pathAnalysis.ts'
import {
  REVENUE_OBSERVATION_MAX_DAYS,
  REVENUE_OBSERVATION_MIN_DAYS,
  revenueMetricUsesProperty,
} from '@/views/dashboard/common/revenueAnalysis.ts'

const props = defineProps<{ context: Record<string, any> }>()
const {
  activeFormulaMetricId, addAttributionEvent, addCalculatedMetricItem, addFunnelStep, addHeatmapComparisonGroup,
  addMetricItem, addPropertyAudience, addRankingMetric, analysisFieldOptions, analysisFieldPickerMode,
  analysisModelContent, analysisModelOptions, appendFormulaAtomicMetric, appendFormulaNumber, appendFormulaOperator,
  appendFormulaParen, attributionEntityFieldOptions, attributionEventFilterExpanded, attributionEventOptions,
  attributionMethodOptions, attributionTargetFilterExpanded, attributionTargetMetricFieldOptions, beginFunnelStepRename,
  beginHeatmapComparisonGroupRename, beginPropertyAudienceRename, beginPropertyMetricRename, beginRetentionEventRename,
  builderAggregationOptions, builderCalculationOperatorOptions, builderFieldOptions, builderFilterOperatorOptions,
  calculatedMetricFormulaText, calculatedMetricTitle, calculatedMetricValidation, cancelFunnelStepRename,
  cancelHeatmapComparisonGroupRename, cancelPropertyAudienceRename, cancelPropertyMetricRename, cancelRetentionEventRename,
  clearFormulaTokens, deleteFormulaToken, distributionEntityFieldOptions, distributionEventLabel, distributionEventOptions,
  distributionEventPropertyOptions, distributionFilterExpanded, distributionSimultaneousMetricFieldOptions, emptyBuilderFilter,
  eventFieldScope, eventFilterFieldOptions, eventUserPropertyOptions, finishFunnelStepRename, finishHeatmapComparisonGroupRename,
  finishPropertyAudienceRename, finishPropertyMetricRename, finishRetentionEventRename, formulaFieldPickerPlaceholder,
  formulaMetricPrecisionText, formulaNumberKeys, formulaParenKeys, formulaTokenText, funnelAliasDraft, funnelAliasEditing,
  funnelEntityFieldOptions, funnelEventOptions, funnelFilterExpanded, funnelRelatedPropertyOptions, handleAnalysisModelChange,
  handleAttributionEventChange, handleAttributionTargetEventChange, handleDistributionEventChange,
  handleDistributionSimultaneousToggle, handleFormulaDisplayClick, handleFormulaEditorFocusout, handleFormulaEditorKeydown,
  handleFunnelRelatedPropertyToggle, handleFunnelStepEventChange, handleIntervalEventChange, handleIntervalRelatedPropertyToggle,
  handleIntervalStartPropertyChange, handleMetricEventChange, handlePropertyGroupFieldChange, handlePropertyGroupModeChange, handleRankingMetricChange,
  handleRetentionEventPropertyChange, handleRetentionRelatedPropertyToggle, handleRetentionSimultaneousToggle, handleRevenueCostToggle,
  handleRevenuePaymentEventChange, hasEffectiveBuilderFilters, heatmapComparisonGroupAliasDraft, heatmapComparisonGroupAliasEditing,
  heatmapFilterExpanded, heatmapMapFileName, intervalEndPropertyOptions, intervalEntityFieldOptions,
  intervalEventFilterFieldOptions, intervalEventOptions, intervalFilterExpanded, intervalStartPropertyOptions,
  isAttributionAnalysis, isDistributionAnalysis, isFunnelAnalysis, isHeatmapAnalysis, isIntervalAnalysis, isPathAnalysis,
  isPropertyAnalysis, isRankingAnalysis, isRetentionAnalysis, isRevenueAnalysis, metricFilterFieldOptions,
  metricMeasureFieldOptions, metricTitle, openHeatmapMapDialog, optionExists, pathEventOptions, pathEventPropertyOptions,
  pathInitialEventOptions, propertyAudienceAliasDraft, propertyAudienceAliasEditing, propertyFieldOptions,
  propertyMetricFieldOptions,
  propertyGroupModeOptions, propertyGroupSetting, propertyGroupSettingsVisible, propertyGroupSupportsTimeSettings,
  propertyGroupTimeGrainOptions, propertyMetricAliasDraft, propertyMetricAliasEditing, rankingEntityFieldOptions,
  rankingEventOptions, rankingMetricFieldOptions, removeAttributionEvent, removeCalculatedMetricItem, removeFunnelStep,
  removeHeatmapComparisonGroup, removeMetricItem, removePropertyAudience, removePropertyGroup, removeRankingMetric,
  retentionAliasDraft, retentionAliasEditing, retentionEntityFieldOptions, retentionEventDefaultDisplayName,
  retentionEventFilterFieldOptions, retentionEventOptions, retentionFilterExpanded, retentionPropertyOptions,
  retentionSimultaneousMetricFieldOptions, revenueEntityFieldOptions, revenueEventOptions, revenueNumericPropertyOptions,
  schemaLoading, setFormulaCursor, sqlBuilder, startEditFormulaAtomicMetric, syncAttributionTargetMetricField,
  syncDistributionSimultaneousMetricField, syncFormulaAtomicMetric, syncPropertyMetric, syncRankingMetricField,
  syncRetentionSimultaneousMetricField, toggleAttributionEventFilter, toggleAttributionTargetFilter, toggleDistributionEventFilter,
  toggleFormulaAtomicMetricFilter, toggleFunnelStepFilter, toggleIntervalEventFilter, toggleRetentionEventFilter,
  trackingEventCatalogOptions, updateDistributionInterval, updateDistributionMetric, updatePropertyGroupSetting,
  updateRevenueMetric,
} = props.context
</script>

<template><div class="sql-builder-content" @click="activeFormulaMetricId = ''">
            <section class="builder-section analysis-model-section">
              <div class="analysis-model-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>分析模型</span>
                  </div>
                </div>
                <el-select
                  v-model="sqlBuilder.analysisModel"
                  class="analysis-model-select"
                  @change="handleAnalysisModelChange"
                >
                  <el-option
                    v-for="option in analysisModelOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </div>
            </section>

            <section v-if="isPropertyAnalysis" class="builder-section property-builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>分析指标</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加属性指标" @click="addMetricItem">
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
              </div>
              <div class="property-metric-list">
                <div v-for="(item, index) in sqlBuilder.metricItems" :key="item.id" class="property-metric-row">
                  <span class="property-metric-index">{{ index + 1 }}</span>
                  <div class="property-metric-body">
                    <div
                      class="property-metric-editor"
                      :class="{
                        'is-active': propertyMetricAliasEditing[item.id],
                        'has-alias': Boolean(item.alias.trim()),
                      }"
                    >
                      <div v-if="propertyMetricAliasEditing[item.id] || item.alias.trim()" class="property-metric-alias-row">
                        <el-input
                          v-if="propertyMetricAliasEditing[item.id]"
                          v-model="propertyMetricAliasDraft[item.id]"
                          class="property-metric-alias-input"
                          clearable
                          maxlength="80"
                          :placeholder="metricTitle(item, index)"
                          :aria-label="`重命名属性指标${index + 1}`"
                          autofocus
                          @keydown.stop
                          @keyup.stop
                          @keydown.enter.prevent="finishPropertyMetricRename(item)"
                          @keydown.esc.prevent="cancelPropertyMetricRename(item)"
                          @blur="finishPropertyMetricRename(item)"
                        />
                        <span v-else class="property-metric-alias-text">{{ item.alias.trim() }}</span>
                      </div>
                      <div class="property-metric-main-row">
                        <BuilderFieldPicker
                          v-model="item.field"
                          :options="propertyMetricFieldOptions"
                          :loading="schemaLoading"
                          mode="property"
                          placeholder="选择属性"
                          @update:modelValue="syncPropertyMetric(item, true)"
                        />
                        <span class="metric-of">的</span>
                        <el-select v-model="item.aggregation" class="property-aggregation-select" @change="syncPropertyMetric(item)">
                          <el-option
                            v-for="option in builderAggregationOptions"
                            :key="option.value"
                            :label="option.label"
                            :value="option.value"
                          />
                        </el-select>
                        <div class="property-metric-actions">
                          <button
                            type="button"
                            class="retention-event-action"
                            :title="`重命名属性指标${index + 1}`"
                            :aria-label="`重命名属性指标${index + 1}`"
                            :disabled="!item.field"
                            @click="beginPropertyMetricRename(item)"
                          >
                            <el-icon><EditPen /></el-icon>
                          </button>
                          <button
                            type="button"
                            class="builder-icon-button danger"
                            :title="`删除属性指标${index + 1}`"
                            :aria-label="`删除属性指标${index + 1}`"
                            @click="removeMetricItem(index)"
                          >
                            <el-icon><Delete /></el-icon>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-if="!sqlBuilder.metricItems.length" class="builder-empty">暂无分析指标</div>
              </div>
            </section>

            <section v-else-if="isHeatmapAnalysis" class="builder-section heatmap-builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>热力指标</span>
                </div>
              </div>
              <div class="heatmap-config-grid">
                <label class="builder-field-label">热力事件</label>
                <div class="heatmap-event-config">
                  <div class="heatmap-event-row">
                    <BuilderFieldPicker
                      v-model="sqlBuilder.heatmap.event"
                      :options="trackingEventCatalogOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择事件"
                    />
                    <button type="button" class="builder-add-link" @click="heatmapFilterExpanded = !heatmapFilterExpanded">
                      <el-icon><Filter /></el-icon><span>筛选条件</span>
                    </button>
                  </div>
                  <BuilderFilterTree
                    v-if="heatmapFilterExpanded"
                    class="heatmap-event-filter-tree"
                    :nodes="sqlBuilder.heatmap.eventFilters"
                    :logic="sqlBuilder.heatmap.eventFilterLogic"
                    :field-options="eventFilterFieldOptions(sqlBuilder.heatmap.event)"
                    :operator-options="builderFilterOperatorOptions"
                    :schema-loading="schemaLoading"
                    picker-mode="filter-property"
                    :filter-property-tabs="['all', 'event', 'user']"
                    empty-text="暂无事件筛选"
                    @update:logic="sqlBuilder.heatmap.eventFilterLogic = $event"
                  />
                </div>
                <label class="builder-field-label">计算</label>
                <div class="heatmap-metric-row">
                  <span>总次数</span>
                  <el-select v-model="sqlBuilder.heatmap.metric.aggregation" class="heatmap-aggregation-select">
                    <el-option v-for="option in builderAggregationOptions" :key="option.value" :label="option.label" :value="option.value" />
                  </el-select>
                  <BuilderFieldPicker
                    v-if="sqlBuilder.heatmap.metric.aggregation !== 'count'"
                    v-model="sqlBuilder.heatmap.metric.field"
                    :options="eventFilterFieldOptions(sqlBuilder.heatmap.event)"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                </div>
                <label class="builder-field-label">地图绘制</label>
                <div class="heatmap-map-picker">
                  <el-button :icon="FolderOpened" @click="openHeatmapMapDialog">选择地图</el-button>
                  <span v-if="heatmapMapFileName" class="heatmap-map-file-name">{{ heatmapMapFileName }}</span>
                  <span v-else class="heatmap-map-file-empty">未选择地图</span>
                </div>
                <label class="builder-field-label">事件坐标</label>
                <div class="heatmap-axis-row">
                  <span>X 轴属性</span>
                  <BuilderFieldPicker v-model="sqlBuilder.heatmap.xField" :options="eventFilterFieldOptions(sqlBuilder.heatmap.event)" :loading="schemaLoading" mode="property" placeholder="选择 X 坐标" />
                  <span>Y 轴属性</span>
                  <BuilderFieldPicker v-model="sqlBuilder.heatmap.yField" :options="eventFilterFieldOptions(sqlBuilder.heatmap.event)" :loading="schemaLoading" mode="property" placeholder="选择 Y 坐标" />
                </div>
              </div>
               <div class="heatmap-comparison-section">
                 <div class="builder-section-head heatmap-comparison-head">
                   <div class="builder-section-title"><BuilderSectionIcon class="builder-section-icon" /><span>多组对比</span></div>
                   <button type="button" class="builder-icon-button" title="添加对比组" aria-label="添加对比组" @click="addHeatmapComparisonGroup"><el-icon><Plus /></el-icon></button>
                 </div>
                 <div v-if="sqlBuilder.heatmap.comparisonGroups.length" class="heatmap-comparison-list">
                   <div v-for="(group, index) in sqlBuilder.heatmap.comparisonGroups" :key="group.id" class="heatmap-comparison-group">
                     <div class="heatmap-comparison-group-head">
                       <span class="property-audience-index">{{ index + 1 }}</span>
                       <el-input v-if="heatmapComparisonGroupAliasEditing[group.id]" v-model="heatmapComparisonGroupAliasDraft[group.id]" size="small" class="property-audience-name-input" :aria-label="`重命名${group.name}`" @keydown.enter.prevent="finishHeatmapComparisonGroupRename(group)" @keydown.esc.prevent="cancelHeatmapComparisonGroupRename(group)" @blur="finishHeatmapComparisonGroupRename(group)" />
                       <span v-else class="property-audience-name">{{ group.name }}</span>
                       <button type="button" class="builder-icon-button" :title="`重命名${group.name}`" @click="beginHeatmapComparisonGroupRename(group)"><el-icon><EditPen /></el-icon></button>
                       <button type="button" class="builder-icon-button danger" :title="`删除${group.name}`" @click="removeHeatmapComparisonGroup(index)"><el-icon><Delete /></el-icon></button>
                     </div>
                     <BuilderFilterTree :nodes="group.filters" :logic="group.filterLogic" :field-options="eventFilterFieldOptions(sqlBuilder.heatmap.event)" :operator-options="builderFilterOperatorOptions" :schema-loading="schemaLoading" picker-mode="filter-property" :filter-property-tabs="['all', 'event', 'user']" :show-toolbar="true" empty-text="暂无筛选条件" @update:logic="group.filterLogic = $event" />
                     <div class="builder-inline-actions property-audience-actions"><button type="button" class="builder-add-link" @click="group.filters.push(emptyBuilderFilter())"><el-icon><Filter /></el-icon><span>筛选条件</span></button></div>
                   </div>
                 </div>
               </div>
             </section>

            <section v-else-if="!isRetentionAnalysis && !isFunnelAnalysis && !isDistributionAnalysis && !isIntervalAnalysis && !isPathAnalysis && !isRevenueAnalysis && !isAttributionAnalysis && !isRankingAnalysis && !isHeatmapAnalysis" class="builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>分析指标</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加指标" @click="addMetricItem">
                    <el-icon><Plus /></el-icon>
                  </button>
                  <button type="button" class="builder-icon-button formula-entry-button" title="添加公式指标" @click.stop="addCalculatedMetricItem">
                    Σ
                  </button>
                </div>
              </div>
              <div class="metric-list">
                <div
                  v-for="(item, index) in sqlBuilder.metricItems"
                  :key="item.id"
                  class="metric-item"
                >
                  <div class="metric-index">{{ index + 1 }}</div>
                  <div class="metric-body">
                    <el-input
                      v-model="item.alias"
                      class="metric-title-input"
                      size="small"
                      clearable
                      :placeholder="metricTitle(item, index)"
                    />
                    <div
                      class="metric-chip-row"
                      :class="{ 'has-metric-field': item.aggregation !== 'count' }"
                    >
                      <BuilderFieldPicker
                        :model-value="item.field"
                        class="metric-field-select"
                        :options="analysisFieldOptions"
                        :loading="schemaLoading"
                        :mode="analysisFieldPickerMode"
                        :placeholder="formulaFieldPickerPlaceholder"
                        @update:modelValue="handleMetricEventChange(item, $event)"
                      />
                      <span class="metric-of">的</span>
                        <el-select
                          v-model="item.aggregation"
                          size="small"
                          class="metric-aggregation"
                          @change="item.metric = optionExists(item.metric, metricMeasureFieldOptions(item)) ? item.metric : ''"
                        >
                        <el-option
                          v-for="option in builderAggregationOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                      <BuilderFieldPicker
                        v-if="item.aggregation !== 'count'"
                        v-model="item.metric"
                        :options="metricMeasureFieldOptions(item)"
                        :loading="schemaLoading"
                        mode="metric"
                        placeholder="计算字段"
                      />
                      <button type="button" class="builder-icon-button danger" @click="removeMetricItem(index)">
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                    <BuilderFilterTree
                      v-if="item.filters.length"
                      :nodes="item.filters"
                      :logic="item.filterLogic"
                      :field-options="metricFilterFieldOptions(item)"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="false"
                      empty-text="暂无指标筛选"
                      @update:logic="item.filterLogic = $event"
                    />
                    <div class="builder-inline-actions">
                      <button type="button" class="builder-add-link" @click="item.filters.push(emptyBuilderFilter())">
                        <el-icon><Plus /></el-icon>
                        <span>筛选条件</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="sqlBuilder.calculatedMetrics.length" class="metric-list formula-metric-list">
                <div
                  v-for="(item, index) in sqlBuilder.calculatedMetrics"
                  :key="item.id"
                  class="metric-item formula-metric-item"
                  @click.stop
                >
                  <div class="metric-index formula-metric-index">
                    {{ sqlBuilder.metricItems.length + index + 1 }}
                  </div>
                  <div class="metric-body">
                    <div class="formula-metric-head">
                      <div class="formula-metric-title-wrap">
                        <el-input
                          v-model="item.alias"
                          class="formula-metric-title-input"
                          size="small"
                          clearable
                          :placeholder="calculatedMetricTitle(item, index)"
                        />
                        <span class="formula-decimal-pill">{{ formulaMetricPrecisionText(item) }}</span>
                      </div>
                      <div class="formula-metric-actions">
                        <button type="button" class="formula-icon-button" title="筛选条件">
                          <el-icon><Filter /></el-icon>
                        </button>
                        <button type="button" class="formula-icon-button" title="公式指标" @click="setFormulaCursor(item, item.tokens.length)">
                          Σ
                        </button>
                        <button type="button" class="formula-icon-button" title="复制公式指标" @click="addCalculatedMetricItem">
                          <el-icon><CopyDocument /></el-icon>
                        </button>
                        <el-dropdown trigger="click" placement="bottom-end">
                          <button type="button" class="formula-icon-button" title="更多操作">
                            <el-icon><MoreFilled /></el-icon>
                          </button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item @click="removeCalculatedMetricItem(index)">
                                删除公式指标
                              </el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                      </div>
                    </div>
                    <div
                      class="formula-editor"
                      @focusin="activeFormulaMetricId = item.id"
                      @focusout="handleFormulaEditorFocusout($event, item)"
                    >
                      <div
                        class="formula-display"
                        :class="{ 'is-empty': !item.tokens.length, 'is-invalid': item.tokens.length && !calculatedMetricValidation(item).valid }"
                        contenteditable="true"
                        spellcheck="false"
                        role="textbox"
                        tabindex="0"
                        @click="handleFormulaDisplayClick($event, item)"
                        @keydown.stop="handleFormulaEditorKeydown($event, item)"
                        @beforeinput.prevent
                        @paste.prevent
                      >
                        <span
                          v-if="!item.tokens.length"
                          class="formula-placeholder"
                        >
                          {{ calculatedMetricFormulaText(item) }}
                        </span>
                        <template v-for="(token, tokenIndex) in item.tokens" :key="`${item.id}-${tokenIndex}`">
                          <span
                            v-if="tokenIndex === 0 && item.formulaCursorIndex === 0"
                            class="formula-cursor"
                          />
                          <template v-if="token.type === 'atomicMetric'">
                            <span
                              class="formula-token-stack"
                              contenteditable="false"
                              @click.stop="startEditFormulaAtomicMetric(item, tokenIndex, token.metric)"
                            >
                              <span class="formula-token-flow">
                                <span
                                  class="formula-token formula-token-atomicMetric"
                                >
                                  <span
                                    class="formula-token-editor-row"
                                    @click.stop="startEditFormulaAtomicMetric(item, tokenIndex, token.metric)"
                                  >
                                    <BuilderFieldPicker
                                      v-model="token.metric.field"
                                      :options="analysisFieldOptions"
                                      :loading="schemaLoading"
                                      :mode="analysisFieldPickerMode"
                                      :placeholder="formulaFieldPickerPlaceholder"
                                      @update:modelValue="syncFormulaAtomicMetric(token.metric, true)"
                                    />
                                    <button
                                      type="button"
                                      class="formula-token-filter"
                                      title="事件筛选"
                                      tabindex="-1"
                                      @click.stop="toggleFormulaAtomicMetricFilter(item, tokenIndex, token.metric)"
                                    >
                                      <el-icon><Filter /></el-icon>
                                    </button>
                                    <span class="formula-token-of">的</span>
                                    <el-select
                                      v-model="token.metric.aggregation"
                                      size="small"
                                      class="formula-token-aggregation"
                                      @change="syncFormulaAtomicMetric(token.metric)"
                                    >
                                      <el-option
                                        v-for="option in builderAggregationOptions"
                                        :key="option.value"
                                        :label="option.label"
                                        :value="option.value"
                                      />
                                    </el-select>
                                    <BuilderFieldPicker
                                      v-if="token.metric.aggregation !== 'count'"
                                      v-model="token.metric.metric"
                                      :options="metricMeasureFieldOptions(token.metric as any)"
                                      :loading="schemaLoading"
                                      mode="metric"
                                      placeholder="计算字段"
                                      @update:modelValue="syncFormulaAtomicMetric(token.metric)"
                                    />
                                  </span>
                                </span>
                                <span
                                  class="formula-insert-target"
                                  :class="{ 'is-active': item.formulaCursorIndex === tokenIndex + 1 }"
                                  contenteditable="false"
                                  @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                                >
                                  <span
                                    v-if="item.formulaCursorIndex === tokenIndex + 1"
                                    class="formula-cursor"
                                  />
                                </span>
                              </span>
                              <BuilderFilterTree
                                v-if="token.metric.filters.length"
                                class="formula-token-filter-tree"
                                :nodes="token.metric.filters"
                                :logic="token.metric.filterLogic"
                                :field-options="metricFilterFieldOptions(token.metric as any)"
                                :operator-options="builderFilterOperatorOptions"
                                :schema-loading="schemaLoading"
                                picker-mode="filter-property"
                                :filter-property-tabs="['all', 'event', 'user']"
                                :show-toolbar="true"
                                empty-text="暂无事件筛选"
                                @update:logic="token.metric.filterLogic = $event"
                              />
                            </span>
                          </template>
                          <template v-else>
                            <span
                              class="formula-token"
                              :class="`formula-token-${token.type}`"
                              contenteditable="false"
                              @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                            >
                              {{ formulaTokenText(token) }}
                            </span>
                          </template>
                          <span
                            v-if="token.type !== 'atomicMetric'"
                            class="formula-insert-target"
                            :class="{ 'is-active': item.formulaCursorIndex === tokenIndex + 1 }"
                            contenteditable="false"
                            @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                          >
                            <span
                              v-if="item.formulaCursorIndex === tokenIndex + 1"
                              class="formula-cursor"
                            />
                          </span>
                        </template>
                      </div>
                      <div
                        v-if="item.tokens.length && !calculatedMetricValidation(item).valid"
                        class="formula-error"
                      >
                        {{ calculatedMetricValidation(item).message }}
                      </div>
                      <div v-if="activeFormulaMetricId === item.id" class="formula-toolbar">
                        <div class="formula-toolbar-panel">
                          <div class="formula-keyboard-layout">
                            <div class="formula-number-pad">
                              <button
                                v-for="numberKey in formulaNumberKeys"
                                :key="numberKey"
                                type="button"
                                class="formula-key-button formula-number-key"
                                @click="appendFormulaNumber(item, numberKey)"
                              >
                                {{ numberKey }}
                              </button>
                            </div>
                            <div class="formula-operator-pad">
                              <button
                                v-for="option in builderCalculationOperatorOptions"
                                :key="option.value"
                                type="button"
                                class="formula-key-button"
                                @click="appendFormulaOperator(item, option.value)"
                              >
                                {{ option.label }}
                              </button>
                              <button
                                v-for="paren in formulaParenKeys"
                                :key="paren"
                                type="button"
                                class="formula-key-button"
                                @click="appendFormulaParen(item, paren)"
                              >
                                {{ paren }}
                              </button>
                              <button type="button" class="formula-key-button formula-delete-key" @click="deleteFormulaToken(item)">
                                ← Del
                              </button>
                            </div>
                            <div class="formula-command-panel">
                              <button type="button" class="formula-action-button" @click="appendFormulaAtomicMetric(item)">
                                <el-icon><Plus /></el-icon>
                                <span>插入事件</span>
                              </button>
                              <span class="formula-shortcut-hint">Ctrl+E</span>
                              <button type="button" class="formula-action-button" @click="clearFormulaTokens(item)">
                                <el-icon><Delete /></el-icon>
                                <span>清空</span>
                              </button>
                              <span class="formula-shortcut-hint">Ctrl+D</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section v-else-if="isRankingAnalysis" class="builder-section ranking-builder-section">
              <div class="ranking-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>排行榜</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="ranking-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.ranking.entityField"
                    :options="rankingEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择排行主体"
                  />
                  <span>进行排名</span>
                </div>
              </div>

              <div class="ranking-metric-block">
                <span class="ranking-config-label">按指标排名</span>
                <div class="ranking-metric-editor">
                  <div class="ranking-metric-row">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.ranking.metric.event"
                      :options="rankingEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择排名指标"
                      @update:modelValue="handleRankingMetricChange(sqlBuilder.ranking.metric, $event)"
                    />
                    <span>的</span>
                    <el-select
                      v-model="sqlBuilder.ranking.metric.aggregation"
                      class="ranking-aggregation-select"
                      @change="syncRankingMetricField(sqlBuilder.ranking.metric)"
                    >
                      <el-option
                        v-for="option in builderAggregationOptions"
                        :key="option.value"
                        :label="option.label"
                        :value="option.value"
                      />
                    </el-select>
                    <BuilderFieldPicker
                      v-if="sqlBuilder.ranking.metric.aggregation !== 'count'"
                      v-model="sqlBuilder.ranking.metric.metricField"
                      :options="rankingMetricFieldOptions(sqlBuilder.ranking.metric)"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="计算字段"
                    />
                    <el-select v-model="sqlBuilder.ranking.metric.direction" class="ranking-direction-select">
                      <el-option label="降序" value="desc" />
                      <el-option label="升序" value="asc" />
                    </el-select>
                  </div>
                </div>
              </div>

              <div class="ranking-tie-block">
                <span class="ranking-config-label">并列名次处理</span>
                <div class="ranking-tie-row">
                  <span>当出现相同值时，将</span>
                  <el-select v-model="sqlBuilder.ranking.tieHandling" class="ranking-tie-select">
                    <el-option label="按默认排序" value="default" />
                    <el-option label="并列且跳过" value="skip" />
                    <el-option label="并列不跳过" value="dense" />
                  </el-select>
                </div>
              </div>

              <div class="ranking-extra-block">
                <div class="ranking-extra-heading">
                  <span class="ranking-config-label">同时展示指标</span>
                  <button type="button" class="builder-add-link" @click="addRankingMetric">
                    <el-icon><Plus /></el-icon>
                    <span>指标</span>
                  </button>
                </div>
                <div v-for="(metric, index) in sqlBuilder.ranking.simultaneousMetrics" :key="metric.id" class="ranking-extra-row">
                  <span class="ranking-extra-index">{{ index + 1 }}</span>
                  <el-input v-model="metric.alias" class="ranking-alias-input" clearable maxlength="80" placeholder="指标名称" />
                  <BuilderFieldPicker
                    :model-value="metric.event"
                    :options="rankingEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择指标"
                    @update:modelValue="handleRankingMetricChange(metric, $event)"
                  />
                  <el-select v-model="metric.aggregation" class="ranking-aggregation-select" @change="syncRankingMetricField(metric)">
                    <el-option
                      v-for="option in builderAggregationOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                  <BuilderFieldPicker
                    v-if="metric.aggregation !== 'count'"
                    v-model="metric.metricField"
                    :options="rankingMetricFieldOptions(metric)"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                  <button type="button" class="builder-icon-button danger" :title="`删除同时展示指标${index + 1}`" @click="removeRankingMetric(index)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.ranking.simultaneousMetrics.length" class="builder-empty">暂无同时展示指标</div>
              </div>

              <div class="ranking-extra-block">
                <div class="ranking-extra-heading">
                  <span class="ranking-config-label">同时展示属性</span>
                  <button type="button" class="builder-add-link" @click="sqlBuilder.ranking.simultaneousProperties.push('')">
                    <el-icon><Plus /></el-icon>
                    <span>属性</span>
                  </button>
                </div>
                <div v-for="(_, index) in sqlBuilder.ranking.simultaneousProperties" :key="index" class="ranking-extra-row ranking-property-row">
                  <span class="ranking-extra-index">{{ index + 1 }}</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.ranking.simultaneousProperties[index]"
                    :options="rankingEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择展示属性"
                  />
                  <button type="button" class="builder-icon-button danger" :title="`删除同时展示属性${index + 1}`" @click="sqlBuilder.ranking.simultaneousProperties.splice(index, 1)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.ranking.simultaneousProperties.length" class="builder-empty">暂无同时展示属性</div>
              </div>
            </section>

            <section v-else-if="isDistributionAnalysis" class="builder-section distribution-builder-section">
              <div class="distribution-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>分布分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="distribution-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.distribution.entityField"
                    :options="distributionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="distribution-event-block">
                <span class="distribution-config-label">参与事件</span>
                <div class="distribution-event-editor" :class="{ 'is-active': distributionFilterExpanded }">
                  <div class="distribution-event-row">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.distribution.event"
                      :options="distributionEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择参与事件"
                      @update:modelValue="handleDistributionEventChange"
                    />
                    <span>的</span>
                    <DistributionMetricPicker
                      :model-value="sqlBuilder.distribution.metric"
                      :event-label="distributionEventLabel"
                      :property-options="distributionEventPropertyOptions"
                      :loading="schemaLoading"
                      :disabled="!sqlBuilder.distribution.event"
                      @update:modelValue="updateDistributionMetric"
                    />
                    <DistributionIntervalSettings
                      :model-value="sqlBuilder.distribution.interval"
                      :disabled="!sqlBuilder.distribution.event"
                      @update:modelValue="updateDistributionInterval"
                    />
                    <button
                      type="button"
                      class="retention-event-action"
                      :class="{ 'is-active': distributionFilterExpanded || hasEffectiveBuilderFilters(sqlBuilder.distribution.eventFilters) }"
                      title="筛选参与事件"
                      aria-label="筛选参与事件"
                      :disabled="!sqlBuilder.distribution.event"
                      @click="toggleDistributionEventFilter"
                    >
                      <el-icon><Filter /></el-icon>
                    </button>
                  </div>
                </div>
                <div v-if="distributionFilterExpanded" class="retention-event-filter-panel">
                  <BuilderFilterTree
                    :nodes="sqlBuilder.distribution.eventFilters"
                    :logic="sqlBuilder.distribution.eventFilterLogic"
                    :field-options="distributionEventPropertyOptions"
                    :operator-options="builderFilterOperatorOptions"
                    :schema-loading="schemaLoading"
                    picker-mode="filter-property"
                    :filter-property-tabs="['all', 'event', 'user']"
                    :show-toolbar="true"
                    empty-text="暂无参与事件筛选"
                    @update:logic="sqlBuilder.distribution.eventFilterLogic = $event"
                    @empty="distributionFilterExpanded = false"
                  />
                </div>
              </div>

              <div class="distribution-simultaneous-block">
                <div class="distribution-switch-row">
                  <span>使用同时展示</span>
                  <el-switch
                    v-model="sqlBuilder.distribution.simultaneous.enabled"
                    @change="handleDistributionSimultaneousToggle"
                  />
                </div>
                <div v-if="sqlBuilder.distribution.simultaneous.enabled" class="distribution-simultaneous-flow">
                  <span>同时展示区间内主体参与</span>
                  <div class="distribution-simultaneous-core-controls">
                    <BuilderFieldPicker
                      v-model="sqlBuilder.distribution.simultaneous.event"
                      :options="distributionEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择参与事件"
                      @update:modelValue="syncDistributionSimultaneousMetricField"
                    />
                    <span>的</span>
                    <el-select
                      v-model="sqlBuilder.distribution.simultaneous.aggregation"
                      size="small"
                      @change="syncDistributionSimultaneousMetricField"
                    >
                      <el-option
                        v-for="option in builderAggregationOptions"
                        :key="option.value"
                        :label="option.label"
                        :value="option.value"
                      />
                    </el-select>
                  </div>
                  <BuilderFieldPicker
                    v-if="sqlBuilder.distribution.simultaneous.aggregation !== 'count'"
                    v-model="sqlBuilder.distribution.simultaneous.metricField"
                    :options="distributionSimultaneousMetricFieldOptions()"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                </div>
              </div>
            </section>

            <section v-else-if="isIntervalAnalysis" class="builder-section interval-builder-section">
              <div class="interval-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>间隔分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="interval-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.interval.entityField"
                    :options="intervalEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="interval-event-stack">
                <div class="interval-event-block">
                  <span class="interval-config-label">起点事件</span>
                  <div class="interval-event-editor" :class="{ 'is-active': intervalFilterExpanded.start }">
                    <div class="interval-event-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.interval.startEvent"
                        :options="intervalEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择起点事件"
                        @update:modelValue="handleIntervalEventChange('start', $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': intervalFilterExpanded.start || hasEffectiveBuilderFilters(sqlBuilder.interval.startEventFilters) }"
                        title="筛选起点事件"
                        aria-label="筛选起点事件"
                        :disabled="!sqlBuilder.interval.startEvent"
                        @click="toggleIntervalEventFilter('start')"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                    </div>
                  </div>
                  <div v-if="intervalFilterExpanded.start" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.interval.startEventFilters"
                      :logic="sqlBuilder.interval.startEventFilterLogic"
                      :field-options="intervalEventFilterFieldOptions('start')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无起点事件筛选"
                      @update:logic="sqlBuilder.interval.startEventFilterLogic = $event"
                      @empty="intervalFilterExpanded.start = false"
                    />
                  </div>
                </div>

                <div class="interval-event-block">
                  <span class="interval-config-label">终点事件</span>
                  <div class="interval-event-editor" :class="{ 'is-active': intervalFilterExpanded.end }">
                    <div class="interval-event-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.interval.endEvent"
                        :options="intervalEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择终点事件"
                        @update:modelValue="handleIntervalEventChange('end', $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': intervalFilterExpanded.end || hasEffectiveBuilderFilters(sqlBuilder.interval.endEventFilters) }"
                        title="筛选终点事件"
                        aria-label="筛选终点事件"
                        :disabled="!sqlBuilder.interval.endEvent"
                        @click="toggleIntervalEventFilter('end')"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                    </div>
                  </div>
                  <div v-if="intervalFilterExpanded.end" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.interval.endEventFilters"
                      :logic="sqlBuilder.interval.endEventFilterLogic"
                      :field-options="intervalEventFilterFieldOptions('end')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无终点事件筛选"
                      @update:logic="sqlBuilder.interval.endEventFilterLogic = $event"
                      @empty="intervalFilterExpanded.end = false"
                    />
                  </div>
                </div>
              </div>

              <div class="interval-option-block">
                <div class="interval-switch-row">
                  <span>使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.interval.relatedProperty.enabled"
                    @change="handleIntervalRelatedPropertyToggle"
                  />
                </div>
                <div v-if="sqlBuilder.interval.relatedProperty.enabled" class="interval-property-match">
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.interval.relatedProperty.startProperty"
                    :options="intervalStartPropertyOptions"
                    :loading="schemaLoading"
                    mode="filter-property"
                    placeholder="起点事件属性"
                    @update:modelValue="handleIntervalStartPropertyChange"
                  />
                  <span>的值与</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.interval.relatedProperty.endProperty"
                    :options="intervalEndPropertyOptions"
                    :loading="schemaLoading"
                    mode="filter-property"
                    placeholder="终点事件属性"
                  />
                  <span>相等</span>
                </div>
              </div>

              <div class="interval-limit-row">
                <span class="interval-config-label">间隔上限</span>
                <div class="interval-limit-content">
                  <p>起点事件到终点事件的间隔不超过</p>
                  <IntervalLimitPicker v-model="sqlBuilder.interval.limitSeconds" />
                </div>
              </div>
            </section>

            <section v-else-if="isPathAnalysis" class="builder-section path-builder-section">
              <div class="path-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>路径分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
              </div>

              <div class="path-config-block">
                <span class="path-config-label">参与分析的事件</span>
                <PathEventList
                  v-model="sqlBuilder.path.events"
                  :event-options="pathEventOptions"
                  :property-options="pathEventPropertyOptions"
                  :loading="schemaLoading"
                  :max-events="PATH_EVENT_LIMIT"
                />
              </div>

              <div class="path-config-block path-initial-event-block">
                <span class="path-config-label">分析路径以</span>
                <div class="path-initial-event-row">
                  <span class="path-initial-event-tag">
                    <el-icon><FolderOpened /></el-icon>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.path.initialEvent"
                      :options="pathInitialEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择初始事件"
                    />
                  </span>
                  <span>作为</span>
                  <span class="path-role-tag">初始事件</span>
                </div>
              </div>

              <div class="path-session-block">
                <span class="path-config-label">会话间隔时长</span>
                  <div class="path-session-row">
                    <PathSessionGapPicker v-model="sqlBuilder.path.sessionGapSeconds" />
                  </div>
              </div>
            </section>

            <section v-else-if="isRevenueAnalysis" class="builder-section revenue-builder-section">
              <div class="revenue-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>收入分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="revenue-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.revenue.entityField"
                    :options="revenueEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="revenue-config-stack">
                <div class="revenue-config-block">
                  <span class="revenue-config-label">同期群</span>
                  <div class="revenue-event-flow">
                    <span>按初始事件</span>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.revenue.initialEvent"
                      :options="revenueEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择初始事件"
                    />
                  </div>
                </div>

                <div class="revenue-config-block">
                  <span class="revenue-config-label">付费事件</span>
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.revenue.paymentEvent"
                    :options="revenueEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择付费事件"
                    @update:modelValue="handleRevenuePaymentEventChange"
                  />
                </div>

                <div class="revenue-config-block">
                  <span class="revenue-config-label">收入口径</span>
                  <div class="revenue-metric-flow">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.revenue.paymentEvent"
                      :options="revenueEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择付费事件"
                      @update:modelValue="handleRevenuePaymentEventChange"
                    />
                    <span>的</span>
                    <RevenueMetricPicker
                      :model-value="sqlBuilder.revenue.metric"
                      :disabled="!sqlBuilder.revenue.paymentEvent"
                      @update:modelValue="updateRevenueMetric"
                    />
                    <BuilderFieldPicker
                      v-if="revenueMetricUsesProperty(sqlBuilder.revenue.metric.method)"
                      v-model="sqlBuilder.revenue.metric.field"
                      :options="revenueNumericPropertyOptions"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="选择数值属性"
                    />
                  </div>
                </div>

                <div class="revenue-cost-block">
                  <div class="revenue-switch-row">
                    <span>成本数据</span>
                    <el-switch
                      v-model="sqlBuilder.revenue.costEnabled"
                      @change="handleRevenueCostToggle"
                    />
                  </div>
                  <div v-if="sqlBuilder.revenue.costEnabled" class="revenue-cost-field-row">
                    <span>成本字段</span>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.revenue.costField"
                      :options="revenueNumericPropertyOptions"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="选择成本字段"
                    />
                  </div>
                </div>

                <div class="revenue-observation-row">
                  <span class="revenue-config-label">观察时长</span>
                  <div>
                    <el-input-number
                      v-model="sqlBuilder.revenue.observationDays"
                      :min="REVENUE_OBSERVATION_MIN_DAYS"
                      :max="REVENUE_OBSERVATION_MAX_DAYS"
                      :precision="0"
                      :controls="false"
                      aria-label="收入分析观察天数"
                    />
                    <span>天</span>
                  </div>
                </div>
              </div>
            </section>

            <section v-else-if="isAttributionAnalysis" class="builder-section attribution-builder-section">
              <div class="attribution-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>归因分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="attribution-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.attribution.entityField"
                    :options="attributionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="attribution-settings">
                <div class="attribution-method-row">
                  <span>归因方式</span>
                  <el-select v-model="sqlBuilder.attribution.method" class="attribution-method-select">
                    <el-option
                      v-for="option in attributionMethodOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>
                <AttributionWindowPicker v-model="sqlBuilder.attribution.window" />
              </div>

              <div class="attribution-divider" />

              <div class="attribution-event-block">
                <span class="attribution-config-label">目标事件</span>
                <div class="attribution-target-row">
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.attribution.targetEvent"
                    :options="attributionEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择目标事件"
                    @update:modelValue="handleAttributionTargetEventChange"
                  />
                  <span>的</span>
                  <el-select
                    v-model="sqlBuilder.attribution.targetMetric.aggregation"
                    class="attribution-metric-select"
                    @change="syncAttributionTargetMetricField"
                  >
                    <el-option
                      v-for="option in builderAggregationOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                  <BuilderFieldPicker
                    v-if="sqlBuilder.attribution.targetMetric.aggregation !== 'count'"
                    v-model="sqlBuilder.attribution.targetMetric.metricField"
                    :options="attributionTargetMetricFieldOptions"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                  <button
                    type="button"
                    class="retention-event-action"
                    :class="{ 'is-active': attributionTargetFilterExpanded || hasEffectiveBuilderFilters(sqlBuilder.attribution.targetEventFilters) }"
                    title="筛选目标事件"
                    aria-label="筛选目标事件"
                    :disabled="!sqlBuilder.attribution.targetEvent"
                    @click="toggleAttributionTargetFilter"
                  >
                    <el-icon><Filter /></el-icon>
                  </button>
                </div>
                <div v-if="attributionTargetFilterExpanded" class="retention-event-filter-panel">
                  <BuilderFilterTree
                    :nodes="sqlBuilder.attribution.targetEventFilters"
                    :logic="sqlBuilder.attribution.targetEventFilterLogic"
                    :field-options="eventFilterFieldOptions(sqlBuilder.attribution.targetEvent)"
                    :operator-options="builderFilterOperatorOptions"
                    :schema-loading="schemaLoading"
                    picker-mode="filter-property"
                    :filter-property-tabs="['all', 'event', 'user']"
                    :show-toolbar="true"
                    empty-text="暂无目标事件筛选"
                    @update:logic="sqlBuilder.attribution.targetEventFilterLogic = $event"
                    @empty="attributionTargetFilterExpanded = false"
                  />
                </div>
              </div>

              <div class="attribution-group-block">
                <div class="attribution-group-heading">
                  <span class="attribution-config-label">分组项</span>
                  <button
                    type="button"
                    class="builder-icon-button"
                    title="添加分组"
                    aria-label="添加分组"
                    @click="sqlBuilder.groups.push('')"
                  >
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
                <div class="group-list attribution-group-list">
                  <div v-for="(_, index) in sqlBuilder.groups" :key="index" class="group-row">
                    <span class="group-index">{{ index + 1 }}</span>
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.groups[index]"
                      :options="builderFieldOptions"
                      :loading="schemaLoading"
                      mode="property"
                      placeholder="分组字段"
                      @update:modelValue="handlePropertyGroupFieldChange(index, $event)"
                    />
                    <button
                      type="button"
                      class="builder-icon-button danger"
                      :title="`删除分组${index + 1}`"
                      :aria-label="`删除分组${index + 1}`"
                      @click="removePropertyGroup(index)"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                  <div v-if="!sqlBuilder.groups.length" class="builder-empty">暂无分组项</div>
                </div>
              </div>

              <el-checkbox v-model="sqlBuilder.attribution.includeDirect" class="attribution-direct-checkbox">
                直接转化参与归因计算
                <el-tooltip content="没有匹配归因事件的目标转化将作为直接转化计入结果。" placement="top">
                  <span class="attribution-info-icon" aria-label="直接转化说明">i</span>
                </el-tooltip>
              </el-checkbox>

              <div class="attribution-event-block attribution-source-block">
                <span class="attribution-config-label">归因事件</span>
                <div v-for="(item, index) in sqlBuilder.attribution.events" :key="item.id" class="attribution-source-item">
                  <span class="attribution-event-index">{{ index + 1 }}</span>
                  <div class="attribution-source-content">
                    <div class="attribution-source-row">
                      <BuilderFieldPicker
                        :model-value="item.event"
                        :options="attributionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择归因事件"
                        @update:modelValue="handleAttributionEventChange(item, $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': attributionEventFilterExpanded[item.id] || hasEffectiveBuilderFilters(item.filters) }"
                        :title="`筛选归因事件${index + 1}`"
                        :aria-label="`筛选归因事件${index + 1}`"
                        :disabled="!item.event"
                        @click="toggleAttributionEventFilter(item)"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                      <button
                        type="button"
                        class="retention-event-action"
                        :title="`删除归因事件${index + 1}`"
                        :aria-label="`删除归因事件${index + 1}`"
                        @click="removeAttributionEvent(index)"
                      >
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                    <div v-if="attributionEventFilterExpanded[item.id]" class="retention-event-filter-panel">
                      <BuilderFilterTree
                        :nodes="item.filters"
                        :logic="item.filterLogic"
                        :field-options="eventFilterFieldOptions(item.event)"
                        :operator-options="builderFilterOperatorOptions"
                        :schema-loading="schemaLoading"
                        picker-mode="filter-property"
                        :filter-property-tabs="['all', 'event', 'user']"
                        :show-toolbar="true"
                        :empty-text="`暂无归因事件${index + 1}筛选`"
                        @update:logic="item.filterLogic = $event"
                        @empty="attributionEventFilterExpanded[item.id] = false"
                      />
                    </div>
                  </div>
                </div>
                <button type="button" class="builder-add-link attribution-add-event" @click="addAttributionEvent">
                  <el-icon><Plus /></el-icon>
                  <span>归因事件</span>
                </button>
              </div>
            </section>

            <section v-else-if="isFunnelAnalysis" class="builder-section funnel-builder-section">
              <div class="funnel-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>漏斗分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="funnel-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.funnel.entityField"
                    :options="funnelEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>
              <div class="funnel-step-list">
                <div v-for="(step, index) in sqlBuilder.funnel.steps" :key="step.id" class="funnel-step-block">
                  <span class="funnel-step-index">{{ index + 1 }}</span>
                  <div class="funnel-step-content">
                    <div
                      class="funnel-step-editor"
                      :class="{
                        'is-active': funnelAliasEditing[step.id] || funnelFilterExpanded[step.id],
                        'has-alias': Boolean(step.alias.trim()),
                      }"
                    >
                      <div v-if="funnelAliasEditing[step.id] || step.alias.trim()" class="funnel-step-alias-row">
                        <el-input
                          v-if="funnelAliasEditing[step.id]"
                          v-model="funnelAliasDraft[step.id]"
                          class="funnel-step-alias-input"
                          clearable
                          maxlength="80"
                          :placeholder="retentionEventDefaultDisplayName(step.event)"
                          :aria-label="`重命名步骤${index + 1}`"
                          autofocus
                          @keydown.stop
                          @keyup.stop
                          @keydown.enter.prevent="finishFunnelStepRename(step)"
                          @keydown.esc.prevent="cancelFunnelStepRename(step)"
                          @blur="finishFunnelStepRename(step)"
                        />
                        <span v-else class="funnel-step-alias-text">{{ step.alias.trim() }}</span>
                      </div>
                      <div class="funnel-step-main-row">
                        <BuilderFieldPicker
                          :model-value="step.event"
                          :options="funnelEventOptions"
                          :loading="schemaLoading"
                          mode="tracking-event"
                          :placeholder="`选择步骤${index + 1}事件`"
                          @update:modelValue="handleFunnelStepEventChange(step, $event)"
                        />
                        <div class="funnel-step-actions">
                          <button
                            type="button"
                            class="retention-event-action"
                            :title="`重命名步骤${index + 1}`"
                            :aria-label="`重命名步骤${index + 1}`"
                            :disabled="!step.event"
                            @click="beginFunnelStepRename(step)"
                          >
                            <el-icon><EditPen /></el-icon>
                          </button>
                          <button
                            type="button"
                            class="retention-event-action"
                            :class="{ 'is-active': funnelFilterExpanded[step.id] || hasEffectiveBuilderFilters(step.filters) }"
                            :title="`筛选步骤${index + 1}`"
                            :aria-label="`筛选步骤${index + 1}`"
                            :disabled="!step.event"
                            @click="toggleFunnelStepFilter(step)"
                          >
                            <el-icon><Filter /></el-icon>
                          </button>
                          <button
                            type="button"
                            class="retention-event-action"
                            :title="`删除步骤${index + 1}`"
                            :aria-label="`删除步骤${index + 1}`"
                            @click="removeFunnelStep(index)"
                          >
                            <el-icon><Delete /></el-icon>
                          </button>
                        </div>
                      </div>
                    </div>
                    <div v-if="funnelFilterExpanded[step.id]" class="retention-event-filter-panel">
                      <BuilderFilterTree
                        :nodes="step.filters"
                        :logic="step.filterLogic"
                        :field-options="eventFilterFieldOptions(step.event)"
                        :operator-options="builderFilterOperatorOptions"
                        :schema-loading="schemaLoading"
                        picker-mode="filter-property"
                        :filter-property-tabs="['all', 'event', 'user']"
                        :show-toolbar="true"
                        :empty-text="`暂无步骤${index + 1}筛选`"
                        @update:logic="step.filterLogic = $event"
                        @empty="funnelFilterExpanded[step.id] = false"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <button type="button" class="builder-add-link funnel-add-step" @click="addFunnelStep">
                <el-icon><Plus /></el-icon>
                <span>添加步骤</span>
              </button>
              <div class="funnel-advanced-options">
                <div class="funnel-option-row">
                  <span>使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.funnel.relatedPropertyEnabled"
                    @change="handleFunnelRelatedPropertyToggle"
                  />
                </div>
                <div v-if="sqlBuilder.funnel.relatedPropertyEnabled" class="funnel-related-property-panel">
                  <span class="funnel-related-property-label">关联属性</span>
                  <div class="funnel-related-property-control">
                    <BuilderFieldPicker
                      v-model="sqlBuilder.funnel.relatedProperty"
                      :options="funnelRelatedPropertyOptions()"
                      :loading="schemaLoading"
                      mode="property"
                      placeholder="选择关联属性"
                    />
                    <span>为关联属性</span>
                    <el-tooltip content="使用该属性匹配同一分析主体在各漏斗步骤中的行为。" placement="top">
                      <el-icon aria-label="关联属性说明"><InfoFilled /></el-icon>
                    </el-tooltip>
                  </div>
                </div>
                <div class="funnel-option-row">
                  <span>分析窗口期</span>
                  <FunnelWindowPicker v-model="sqlBuilder.funnel.window" />
                </div>
              </div>
            </section>

            <section v-else class="builder-section retention-builder-section">
              <div class="retention-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>留存分析</span>
                    <el-tooltip v-if="analysisModelContent" :content="analysisModelContent" placement="top"><el-icon class="analysis-model-info-icon" aria-label="分析模型说明"><InfoFilled /></el-icon></el-tooltip>
                  </div>
                </div>
                <div class="retention-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.retention.entityField"
                    :options="retentionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>
              <div class="retention-event-stack">
                <div class="retention-field-block">
                  <span class="retention-config-label">初始事件</span>
                  <div
                    class="retention-event-editor"
                    :class="{
                      'is-active': retentionAliasEditing.initial || retentionFilterExpanded.initial,
                      'has-alias': Boolean(sqlBuilder.retention.initialEventAlias.trim()),
                    }"
                  >
                    <div
                      v-if="retentionAliasEditing.initial || sqlBuilder.retention.initialEventAlias.trim()"
                      class="retention-event-alias-row"
                    >
                      <el-input
                        v-if="retentionAliasEditing.initial"
                        v-model="retentionAliasDraft.initial"
                        class="retention-event-alias-input"
                        clearable
                        maxlength="80"
                        :placeholder="retentionEventDefaultDisplayName(sqlBuilder.retention.initialEvent)"
                        aria-label="重命名初始事件"
                        autofocus
                        @keydown.stop
                        @keyup.stop
                        @keydown.enter.prevent="finishRetentionEventRename('initial')"
                        @keydown.esc.prevent="cancelRetentionEventRename('initial')"
                        @blur="finishRetentionEventRename('initial')"
                      />
                      <span v-else class="retention-event-alias-text">
                        {{ sqlBuilder.retention.initialEventAlias.trim() }}
                      </span>
                    </div>
                    <div class="retention-event-main-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.retention.initialEvent"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择初始事件"
                        @update:modelValue="handleRetentionEventPropertyChange('initial', $event)"
                      />
                      <div class="retention-event-actions">
                        <button
                          type="button"
                          class="retention-event-action"
                          title="重命名初始事件"
                          aria-label="重命名初始事件"
                          :disabled="!sqlBuilder.retention.initialEvent"
                          @click="beginRetentionEventRename('initial')"
                        >
                          <el-icon><EditPen /></el-icon>
                        </button>
                        <button
                          type="button"
                          class="retention-event-action"
                          :class="{ 'is-active': retentionFilterExpanded.initial || hasEffectiveBuilderFilters(sqlBuilder.retention.initialEventFilters) }"
                          title="筛选初始事件"
                          aria-label="筛选初始事件"
                          :disabled="!sqlBuilder.retention.initialEvent"
                          @click="toggleRetentionEventFilter('initial')"
                        >
                          <el-icon><Filter /></el-icon>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div v-if="retentionFilterExpanded.initial" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.retention.initialEventFilters"
                      :logic="sqlBuilder.retention.initialEventFilterLogic"
                      :field-options="retentionEventFilterFieldOptions('initial')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无初始事件筛选"
                      @update:logic="sqlBuilder.retention.initialEventFilterLogic = $event"
                      @empty="retentionFilterExpanded.initial = false"
                    />
                  </div>
                </div>
                <div class="retention-field-block">
                  <span class="retention-config-label">回访事件</span>
                  <div
                    class="retention-event-editor"
                    :class="{
                      'is-active': retentionAliasEditing.return || retentionFilterExpanded.return,
                      'has-alias': Boolean(sqlBuilder.retention.returnEventAlias.trim()),
                    }"
                  >
                    <div
                      v-if="retentionAliasEditing.return || sqlBuilder.retention.returnEventAlias.trim()"
                      class="retention-event-alias-row"
                    >
                      <el-input
                        v-if="retentionAliasEditing.return"
                        v-model="retentionAliasDraft.return"
                        class="retention-event-alias-input"
                        clearable
                        maxlength="80"
                        :placeholder="retentionEventDefaultDisplayName(sqlBuilder.retention.returnEvent)"
                        aria-label="重命名回访事件"
                        autofocus
                        @keydown.stop
                        @keyup.stop
                        @keydown.enter.prevent="finishRetentionEventRename('return')"
                        @keydown.esc.prevent="cancelRetentionEventRename('return')"
                        @blur="finishRetentionEventRename('return')"
                      />
                      <span v-else class="retention-event-alias-text">
                        {{ sqlBuilder.retention.returnEventAlias.trim() }}
                      </span>
                    </div>
                    <div class="retention-event-main-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.retention.returnEvent"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择回访事件"
                        @update:modelValue="handleRetentionEventPropertyChange('return', $event)"
                      />
                      <div class="retention-event-actions">
                        <button
                          type="button"
                          class="retention-event-action"
                          title="重命名回访事件"
                          aria-label="重命名回访事件"
                          :disabled="!sqlBuilder.retention.returnEvent"
                          @click="beginRetentionEventRename('return')"
                        >
                          <el-icon><EditPen /></el-icon>
                        </button>
                        <button
                          type="button"
                          class="retention-event-action"
                          :class="{ 'is-active': retentionFilterExpanded.return || hasEffectiveBuilderFilters(sqlBuilder.retention.returnEventFilters) }"
                          title="筛选回访事件"
                          aria-label="筛选回访事件"
                          :disabled="!sqlBuilder.retention.returnEvent"
                          @click="toggleRetentionEventFilter('return')"
                        >
                          <el-icon><Filter /></el-icon>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div v-if="retentionFilterExpanded.return" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.retention.returnEventFilters"
                      :logic="sqlBuilder.retention.returnEventFilterLogic"
                      :field-options="retentionEventFilterFieldOptions('return')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无回访事件筛选"
                      @update:logic="sqlBuilder.retention.returnEventFilterLogic = $event"
                      @empty="retentionFilterExpanded.return = false"
                    />
                  </div>
                </div>
              </div>
              <div class="retention-advanced-options">
                <div class="retention-option-block">
                  <span class="retention-option-title">使用同时展示</span>
                  <el-switch
                    v-model="sqlBuilder.retention.simultaneous.enabled"
                    @change="handleRetentionSimultaneousToggle"
                  />
                  <template v-if="sqlBuilder.retention.simultaneous.enabled">
                    <span class="retention-option-description">同时展示回访的用户参与</span>
                    <div
                      class="retention-option-flow"
                      :class="{ 'has-metric-field': sqlBuilder.retention.simultaneous.aggregation !== 'count' }"
                    >
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.simultaneous.event"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择参与事件"
                        @update:modelValue="handleRetentionEventPropertyChange('simultaneous', $event)"
                      />
                      <span>的</span>
                      <el-select
                        v-model="sqlBuilder.retention.simultaneous.aggregation"
                        size="small"
                        @change="syncRetentionSimultaneousMetricField"
                      >
                        <el-option
                          v-for="option in builderAggregationOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                      <BuilderFieldPicker
                        v-if="sqlBuilder.retention.simultaneous.aggregation !== 'count'"
                        v-model="sqlBuilder.retention.simultaneous.metricField"
                        :options="retentionSimultaneousMetricFieldOptions()"
                        :loading="schemaLoading"
                        mode="metric"
                        placeholder="计算字段"
                      />
                    </div>
                  </template>
                </div>

                <div class="retention-option-block">
                  <span class="retention-option-title">使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.retention.relatedProperty.enabled"
                    @change="handleRetentionRelatedPropertyToggle"
                  />
                  <template v-if="sqlBuilder.retention.relatedProperty.enabled">
                    <div class="retention-property-flow">
                      <span>初始事件的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.initialProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.initialEvent)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>与</span>
                    </div>
                    <div class="retention-property-flow">
                      <span>回访事件的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.returnProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.returnEvent)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>{{ sqlBuilder.retention.simultaneous.enabled ? '与' : '的值相等' }}</span>
                    </div>
                    <div v-if="sqlBuilder.retention.simultaneous.enabled" class="retention-property-flow">
                      <span>同时展示的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.simultaneousProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.simultaneous.event)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>的值相等</span>
                    </div>
                    <span class="retention-option-title">关联属性作为分组展示</span>
                    <el-switch v-model="sqlBuilder.retention.relatedProperty.asGroup" />
                  </template>
                </div>
              </div>
            </section>

            <section v-if="!isAttributionAnalysis" class="builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>全局筛选</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加筛选条件" @click="sqlBuilder.globalFilters.push(emptyBuilderFilter())">
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
              </div>
              <BuilderFilterTree
                :nodes="sqlBuilder.globalFilters"
                :logic="sqlBuilder.globalFilterLogic"
                :field-options="isPropertyAnalysis ? propertyFieldOptions : eventUserPropertyOptions"
                :operator-options="builderFilterOperatorOptions"
                :schema-loading="schemaLoading"
                :picker-mode="isPropertyAnalysis && eventFieldScope.status !== 'active' ? 'property' : 'filter-property'"
                :filter-property-tabs="['user']"
                :show-toolbar="false"
                empty-text="暂无全局筛选"
                @update:logic="sqlBuilder.globalFilterLogic = $event"
              />
            </section>

            <section class="builder-section">
              <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <template v-if="isPropertyAnalysis">
                      <span>按</span>
                      <el-select
                        v-model="sqlBuilder.property.groupMode"
                        class="property-group-mode-select"
                        size="small"
                        :teleported="false"
                        @change="handlePropertyGroupModeChange"
                      >
                        <el-option
                          v-for="option in propertyGroupModeOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                      <span>进行分组统计</span>
                    </template>
                  <span v-else>分组项</span>
                </div>
                <div class="builder-section-actions">
                  <button
                    type="button"
                    class="builder-icon-button"
                    :title="isPropertyAnalysis && sqlBuilder.property.groupMode === 'audience' ? '添加人群' : '添加分组项'"
                    @click="isPropertyAnalysis && sqlBuilder.property.groupMode === 'audience' ? addPropertyAudience() : sqlBuilder.groups.push('')"
                  >
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
              </div>
              <div v-if="isPropertyAnalysis && sqlBuilder.property.groupMode === 'audience'" class="property-audience-list">
                <div
                  v-for="(group, index) in sqlBuilder.property.audiences"
                  :key="group.id"
                  class="property-audience-group"
                >
                  <div class="property-audience-head">
                    <span class="property-audience-index">{{ index + 1 }}</span>
                    <el-input
                      v-if="propertyAudienceAliasEditing[group.id]"
                      v-model="propertyAudienceAliasDraft[group.id]"
                      class="property-audience-name-input"
                      size="small"
                      :aria-label="`重命名${group.name}`"
                      @keydown.enter.prevent="finishPropertyAudienceRename(group)"
                      @keydown.esc.prevent="cancelPropertyAudienceRename(group)"
                      @blur="finishPropertyAudienceRename(group)"
                    />
                    <span v-else class="property-audience-name">{{ group.name }}</span>
                    <button
                      type="button"
                      class="builder-icon-button property-audience-edit"
                      :title="`重命名${group.name}`"
                      :aria-label="`重命名${group.name}`"
                      @click="beginPropertyAudienceRename(group)"
                    >
                      <el-icon><EditPen /></el-icon>
                    </button>
                    <button
                      type="button"
                      class="builder-icon-button danger property-audience-delete"
                      :title="`删除${group.name}`"
                      :aria-label="`删除${group.name}`"
                      @click="removePropertyAudience(index)"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                  <div v-if="group.filters.length" class="property-audience-filter-tree">
                    <BuilderFilterTree
                      :nodes="group.filters"
                      :logic="group.filterLogic"
                      :field-options="eventUserPropertyOptions"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['user']"
                      :show-toolbar="true"
                      empty-text="暂无筛选条件"
                      @update:logic="group.filterLogic = $event"
                    />
                  </div>
                  <div v-else class="property-audience-all-users">全部用户</div>
                  <div class="builder-inline-actions property-audience-actions">
                    <button type="button" class="builder-add-link" @click="group.filters.push(emptyBuilderFilter())">
                      <el-icon><Plus /></el-icon>
                      <span>筛选条件</span>
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="group-list">
                <div v-for="(_, index) in sqlBuilder.groups" :key="index" class="group-row">
                  <span class="group-index">{{ index + 1 }}</span>
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.groups[index]"
                    :options="isPropertyAnalysis ? propertyFieldOptions : builderFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="分组字段"
                    @update:modelValue="handlePropertyGroupFieldChange(index, $event)"
                  />
                  <el-popover
                    v-if="isPropertyAnalysis && propertyGroupSupportsTimeSettings(sqlBuilder.groups[index])"
                    v-model:visible="propertyGroupSettingsVisible[sqlBuilder.groups[index]]"
                    placement="bottom-start"
                    :width="300"
                    trigger="click"
                    :teleported="false"
                  >
                    <template #reference>
                      <button
                        type="button"
                        class="builder-icon-button property-group-settings-button"
                        title="设置时间分组"
                        :aria-label="`设置时间分组${index + 1}`"
                      >
                        <el-icon><Setting /></el-icon>
                      </button>
                    </template>
                    <div class="property-group-settings">
                      <div class="property-group-settings-title">分组方式</div>
                      <el-radio-group
                        :model-value="propertyGroupSetting(sqlBuilder.groups[index]).summarize ? 'summarize' : 'raw'"
                        @update:modelValue="updatePropertyGroupSetting(sqlBuilder.groups[index], { summarize: $event === 'summarize' })"
                      >
                        <el-radio value="summarize">汇总</el-radio>
                        <el-radio value="raw">不汇总</el-radio>
                      </el-radio-group>
                      <el-select
                        v-if="propertyGroupSetting(sqlBuilder.groups[index]).summarize"
                        class="property-group-time-grain-select"
                        :model-value="propertyGroupSetting(sqlBuilder.groups[index]).timeGrain"
                        @update:modelValue="updatePropertyGroupSetting(sqlBuilder.groups[index], { timeGrain: $event })"
                      >
                        <el-option
                          v-for="option in propertyGroupTimeGrainOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                    </div>
                  </el-popover>
                  <button
                    type="button"
                    class="builder-icon-button danger"
                    @click="removePropertyGroup(index)"
                  >
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.groups.length" class="builder-empty">暂无分组项</div>
              </div>
            </section>
</div></template>

<style scoped lang="less">
.sql-editor-body {
  padding-right: 4px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.muted {
  color: #8f959e;
  font-size: 13px;
}

.editor-alert {
  margin-bottom: 16px;
}

.source-section-toggle {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 12px;
  margin: 0 0 12px;
  border: 1px solid rgba(31, 35, 41, 0.1);
  border-radius: 6px;
  background: #fff;
}

.source-section-title {
  flex: 0 0 auto;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.source-inline-checkbox {
  height: 24px;
  margin-right: 0;
}

.source-inline-checkbox :deep(.el-checkbox__label) {
  font-size: 13px;
}

.sql-builder-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.builder-advice-button {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #eef3ff;
  color: #1f54d8;
  cursor: pointer;
}

.builder-advice-button.warning {
  background: #fff1f0;
  color: #f04438;
}

.builder-advice-button :deep(.el-icon) {
  font-size: 16px;
}

.sql-builder-panel {
  min-height: 580px;
  max-height: 620px;
  margin-bottom: 10px;
  border: 1px solid rgba(31, 35, 41, 0.1);
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sql-builder-header {
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid rgba(31, 35, 41, 0.08);
  background: #fff;
}

.sql-builder-tabs {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px;
  border-radius: 6px;
  background: #f4f6fb;
}

.sql-builder-tabs button {
  height: 24px;
  padding: 0 9px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #646a73;
  cursor: pointer;
  font-size: 12px;
}

.sql-builder-tabs button.active {
  background: #fff;
  color: #1f54d8;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(31, 35, 41, 0.08);
}

.builder-advice-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.builder-advice-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.builder-advice-title {
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.builder-advice-text {
  color: #4e5969;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.builder-advice-list {
  margin: 0;
  padding-left: 18px;
  color: #4e5969;
  font-size: 13px;
  line-height: 1.7;
}

.sql-builder-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 16px 22px 0;
}

.sql-builder-builder-pane {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.builder-section {
  padding: 0 0 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f2f6;
}

.builder-section:last-of-type {
  margin-bottom: 0;
  border-bottom: 0;
}

.builder-section-head {
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.builder-section-title {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: 7px;
  white-space: nowrap;
}

.builder-section-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  color: #1f2329;
}

.builder-section-actions {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.analysis-model-select {
  width: 220px;
}

.analysis-model-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.analysis-model-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.retention-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.funnel-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.distribution-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.ranking-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.ranking-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.ranking-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.ranking-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.ranking-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.ranking-metric-block,
.ranking-extra-block {
  margin-top: 20px;
}

.ranking-metric-editor {
  display: grid;
  gap: 10px;
  max-width: 980px;
}

.ranking-metric-row,
.ranking-extra-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.ranking-metric-row :deep(.builder-field-picker),
.ranking-extra-row :deep(.builder-field-picker) {
  min-width: 150px;
  flex: 1 1 190px;
}

.ranking-aggregation-select {
  width: 120px;
  flex: 0 0 120px;
}

.ranking-direction-select {
  width: 92px;
  flex: 0 0 92px;
}

.ranking-tie-block {
  margin-top: 22px;
}

.ranking-tie-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #505968;
  font-size: 13px;
}

.ranking-tie-select {
  width: 128px;
}

.ranking-extra-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ranking-extra-heading .ranking-config-label {
  margin: 0;
}

.ranking-extra-row {
  margin-top: 10px;
}

.ranking-extra-index {
  flex: 0 0 20px;
  color: #8a93a3;
  text-align: center;
}

.ranking-alias-input {
  width: 150px;
  flex: 0 1 150px;
}

.ranking-property-row :deep(.builder-field-picker) {
  max-width: 360px;
}

.interval-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.interval-heading-row .builder-section-head {
  width: auto;
  flex: 0 0 auto;
}

.interval-subject-line {
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  width: auto;
  min-width: 0;
  gap: 8px;
  color: #303643;
  font-size: 13px;
}

.interval-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.interval-event-stack {
  display: grid;
  gap: 18px;
  margin-top: 20px;
}

.interval-event-block {
  min-width: 0;
}

.interval-config-label {
  display: block;
  margin-bottom: 7px;
  color: #8a93a3;
  font-size: 12px;
}

.interval-event-editor {
  min-width: 0;
  padding: 5px 24px 7px 0;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.interval-event-editor:hover,
.interval-event-editor:focus-within,
.interval-event-editor.is-active {
  background: #f7f8fa;
}

.interval-event-row {
  display: grid;
  grid-template-columns: minmax(190px, 360px) 30px;
  align-items: center;
  gap: 8px;
}

.interval-event-row :deep(.builder-field-picker),
.interval-property-match :deep(.builder-field-picker) {
  min-width: 0;
}

.interval-option-block {
  display: grid;
  gap: 12px;
  margin-top: 24px;
}

.interval-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: min(100%, 360px);
  color: #4b5563;
  font-size: 13px;
}

.interval-property-match {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) auto minmax(150px, 1fr) auto;
  align-items: center;
  gap: 8px;
  max-width: 760px;
  color: #6b7280;
  font-size: 13px;
}

.interval-limit-row {
  margin-top: 24px;
}

.interval-limit-row .interval-config-label {
  margin-bottom: 7px;
}

.interval-limit-row p {
  margin: 0;
  color: #4b5563;
  font-size: 13px;
}

.interval-limit-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.analysis-model-info-icon {
  color: #8a93a3;
  cursor: help;
  font-size: 14px;
}

.path-config-block,
.path-session-block {
  margin-top: 20px;
}

.path-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.path-role-tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 6px;
  color: #374151;
  background: #f0f2f6;
  white-space: nowrap;
}

.path-initial-event-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #707988;
  font-size: 13px;
}

.path-initial-event-tag {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  border-radius: 6px;
  color: #374151;
  background: #f0f2f6;
  line-height: 26px;
}

.path-initial-event-tag :deep(.builder-field-picker-trigger) {
  min-height: 24px;
  max-width: 180px;
  padding: 0;
  color: #374151;
  background: transparent;
  line-height: 24px;
}

.path-initial-event-tag :deep(.builder-field-picker-trigger:hover) {
  background: transparent;
}

.path-initial-event-tag :deep(.builder-field-picker-arrow) {
  display: none;
}

.path-session-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #505968;
  font-size: 13px;
}

.path-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid #aab2bf;
  border-radius: 50%;
  color: #8b94a2;
  font-size: 11px;
  font-style: normal;
}

.path-session-exact {
  color: #9aa2af;
  font-size: 12px;
}

.revenue-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.revenue-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.attribution-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
}

.attribution-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.revenue-subject-line,
.attribution-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.revenue-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.revenue-config-stack {
  display: grid;
  gap: 20px;
}

.revenue-config-block {
  display: grid;
  justify-items: start;
  gap: 7px;
  min-width: 0;
}

.revenue-config-label,
.attribution-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.attribution-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.attribution-settings {
  display: grid;
  gap: 14px;
  color: #505968;
  font-size: 13px;
}

.attribution-method-row {
  display: grid;
  grid-template-columns: 64px minmax(100px, 160px);
  align-items: center;
  gap: 8px;
}

.attribution-method-select {
  width: 100%;
}

.attribution-divider {
  height: 1px;
  margin: 18px -22px;
  background: #eef0f4;
}

.attribution-event-block {
  min-width: 0;
}

.attribution-group-block {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #eef0f4;
}

.attribution-group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
}

.attribution-group-heading .attribution-config-label {
  margin-bottom: 0;
}

.attribution-group-list {
  margin-top: 4px;
}

.revenue-event-flow,
.revenue-metric-flow,
.revenue-cost-field-row,
.revenue-observation-row > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.attribution-target-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.revenue-config-block > :deep(.builder-field-picker),
.revenue-event-flow :deep(.builder-field-picker),
.revenue-metric-flow :deep(.builder-field-picker),
.revenue-cost-field-row :deep(.builder-field-picker) {
  min-width: 170px;
  max-width: 300px;
}

.revenue-cost-block {
  display: grid;
  gap: 10px;
  justify-items: start;
}

.revenue-switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #505968;
  font-size: 13px;
}

.revenue-cost-field-row {
  padding-left: 18px;
}

.revenue-observation-row {
  display: grid;
  justify-items: start;
  gap: 7px;
}

.revenue-observation-row :deep(.el-input-number) {
  width: 80px;
  color: #6b7280;
  font-size: 13px;
}

.attribution-target-row :deep(.builder-field-picker) {
  min-width: 150px;
}

.attribution-metric-select {
  width: 104px;
}

.attribution-direct-checkbox {
  margin-top: 14px;
}

.attribution-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 4px;
  border: 1px solid #aab2bf;
  border-radius: 50%;
  color: #8b94a2;
  font-size: 10px;
  font-style: normal;
}

.attribution-source-block {
  margin-top: 22px;
}

.attribution-source-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  margin-bottom: 8px;
}

.attribution-event-index {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-top: 3px;
  border-radius: 7px;
  color: #fff;
  background: #252b56;
  font-size: 12px;
}

.attribution-source-content {
  flex: 1 1 auto;
  min-width: 0;
}

.attribution-source-row {
  display: grid;
  grid-template-columns: minmax(190px, 360px) 30px 30px;
  align-items: center;
  gap: 4px;
  min-height: 30px;
}

.attribution-add-event {
  margin: 4px 0 0 34px;
}

.distribution-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.distribution-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

.distribution-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.distribution-event-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}

.distribution-config-label {
  color: #8a93a3;
  font-size: 12px;
}

.distribution-event-editor {
  width: 100%;
  min-width: 0;
  padding: 6px 8px 8px 0;
  transition: background-color 0.16s ease;
}

.distribution-event-editor:hover,
.distribution-event-editor:focus-within,
.distribution-event-editor.is-active {
  background: #f7f8fa;
}

.distribution-event-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 13px;
}

.distribution-event-row :deep(.builder-field-picker) {
  min-width: 0;
}

.distribution-simultaneous-block {
  margin-top: 22px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  color: #505968;
  font-size: 12px;
}

.distribution-switch-row,
.distribution-simultaneous-flow {
  display: flex;
  align-items: center;
  gap: 10px;
}

.distribution-simultaneous-flow {
  flex-wrap: wrap;
}

.distribution-simultaneous-core-controls {
  min-width: 353px;
  display: grid;
  grid-template-columns: minmax(160px, 280px) auto 160px;
  align-items: center;
  gap: 10px;
}

.distribution-simultaneous-core-controls :deep(.builder-field-picker-trigger) {
  width: 100%;
  min-width: 0;
}

.distribution-simultaneous-core-controls :deep(.el-select) {
  width: 160px;
}

.funnel-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.funnel-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

.funnel-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.funnel-step-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.funnel-step-block {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
}

.funnel-step-index {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-top: 5px;
  border-radius: 7px;
  color: #fff;
  background: #252b56;
  font-size: 12px;
}

.funnel-step-content {
  flex: 1 1 auto;
  min-width: 0;
}

.funnel-step-editor {
  width: 100%;
  min-width: 0;
  padding: 5px 0 7px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: background-color 0.16s ease;
}

.funnel-step-editor:hover,
.funnel-step-editor:focus-within,
.funnel-step-editor.is-active {
  background: #f7f8fa;
}

.funnel-step-alias-row,
.funnel-step-main-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
}

.funnel-step-main-row {
  min-height: 28px;
  justify-content: space-between;
  gap: 12px;
}

.funnel-step-main-row :deep(.builder-field-picker) {
  min-width: 0;
}

.funnel-step-alias-input {
  width: min(260px, 100%);
}

.funnel-step-alias-input :deep(.ed-input__wrapper),
.funnel-step-alias-input :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.funnel-step-alias-input :deep(.ed-input__wrapper:hover),
.funnel-step-alias-input :deep(.ed-input__wrapper.is-focus),
.funnel-step-alias-input :deep(.el-input__wrapper:hover),
.funnel-step-alias-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 -1px 0 #2f6bff;
}

.funnel-step-alias-text {
  min-width: 0;
  color: #303643;
  font-size: 14px;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.funnel-step-actions {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.16s ease;
}

.funnel-step-editor:hover .funnel-step-actions,
.funnel-step-editor:focus-within .funnel-step-actions,
.funnel-step-editor.is-active .funnel-step-actions {
  opacity: 1;
  visibility: visible;
}

.funnel-related-property-panel {
  width: min(100%, 360px);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 2px;
  padding: 12px 14px;
  border: 1px solid #e3e7ee;
  border-radius: 6px;
  background: #fff;
  color: #6b7280;
  font-size: 12px;
}

.funnel-related-property-label {
  color: #505968;
  line-height: 18px;
}

.funnel-related-property-control {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.funnel-related-property-control :deep(.builder-field-picker) {
  min-width: 0;
  flex: 0 1 180px;
}

.funnel-related-property-control :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.funnel-related-property-control > span {
  flex: none;
  white-space: nowrap;
}

.funnel-related-property-control .el-icon {
  flex: none;
  color: #8b93a1;
  cursor: help;
}

.funnel-add-step {
  margin: 12px 0 0 34px;
}

.funnel-advanced-options {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  margin-top: 24px;
  color: #505968;
  font-size: 12px;
}

.funnel-option-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.funnel-option-row .el-input-number {
  width: 104px;
}

.retention-heading-row .builder-section-head {
  flex: 0 0 120px;
  margin-bottom: 0;
}

.retention-subject-line {
  width: auto;
  flex: 1 1 auto;
  box-sizing: border-box;
  padding: 0;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

@media (max-width: 720px) {
  .analysis-model-row,
  .retention-heading-row,
  .funnel-heading-row,
  .distribution-heading-row,
  .interval-heading-row,
  .revenue-heading-row,
  .ranking-heading-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .attribution-heading-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .attribution-heading-row .attribution-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .attribution-target-row {
    flex-wrap: wrap;
  }

  .attribution-source-row {
    grid-template-columns: minmax(0, 1fr) 30px 30px;
  }

  .retention-heading-row .retention-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .funnel-heading-row .funnel-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .path-heading-row {
    gap: 10px;
  }

  .distribution-heading-row .distribution-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .interval-heading-row .interval-subject-line {
    width: 100%;
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .revenue-heading-row .revenue-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .ranking-heading-row .ranking-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .revenue-event-flow,
  .revenue-metric-flow,
  .revenue-cost-field-row {
    flex-wrap: wrap;
  }

  .distribution-event-row {
    flex-wrap: wrap;
  }

  .distribution-simultaneous-core-controls {
    width: 100%;
    min-width: 0;
    flex: 1 1 100%;
    grid-template-columns: minmax(120px, 1fr) auto minmax(120px, 160px);
  }

  .distribution-simultaneous-core-controls :deep(.el-select) {
    width: 100%;
  }

  .ranking-metric-row,
  .ranking-extra-row {
    flex-wrap: wrap;
  }

  .ranking-metric-row :deep(.builder-field-picker),
  .ranking-extra-row :deep(.builder-field-picker),
  .ranking-alias-input {
    flex-basis: min(100%, 280px);
  }

  .interval-event-row,
  .interval-property-match {
    grid-template-columns: minmax(0, 1fr);
  }

  .interval-event-row .retention-event-action {
    justify-self: start;
  }

  .interval-limit-row {
    width: 100%;
  }

  .interval-limit-content {
    flex-wrap: wrap;
  }

  .path-initial-event-row {
    max-width: 100%;
    flex-wrap: wrap;
  }

  .path-session-row {
    flex-wrap: wrap;
  }
}

.retention-subject-line :deep(.builder-field-picker-trigger),
.retention-option-flow :deep(.builder-field-picker-trigger),
.retention-property-flow :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.retention-event-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.retention-field-block {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}

.retention-field-block :deep(.builder-field-picker-trigger) {
  width: auto;
  max-width: 100%;
}

.retention-event-editor {
  width: 100%;
  min-width: 0;
  padding: 5px 24px 7px 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  transition: background-color 0.16s ease;
}

.retention-event-editor:hover,
.retention-event-editor:focus-within,
.retention-event-editor.is-active {
  background: #f7f8fa;
}

.retention-event-alias-row,
.retention-event-main-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
}

.retention-event-main-row {
  min-height: 28px;
  justify-content: space-between;
  gap: 12px;
}

.retention-event-main-row :deep(.builder-field-picker) {
  min-width: 0;
}

.retention-event-alias-input {
  width: min(260px, 100%);
}

.retention-event-alias-input :deep(.ed-input__wrapper),
.retention-event-alias-input :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.retention-event-alias-input :deep(.ed-input__wrapper:hover),
.retention-event-alias-input :deep(.ed-input__wrapper.is-focus),
.retention-event-alias-input :deep(.el-input__wrapper:hover),
.retention-event-alias-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 -1px 0 #2f6bff;
}

.retention-event-alias-text {
  min-width: 0;
  color: #303643;
  font-size: 14px;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.retention-event-actions {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.16s ease;
}

.retention-event-editor:hover .retention-event-actions,
.retention-event-editor:focus-within .retention-event-actions,
.retention-event-editor.is-active .retention-event-actions {
  opacity: 1;
  visibility: visible;
}

.retention-event-action {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #7b8190;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}

.retention-event-action:hover,
.retention-event-action.is-active {
  background: #eef3ff;
  color: #2f6bff;
}

.retention-event-action:disabled {
  background: transparent;
  color: #c4c9d2;
  cursor: not-allowed;
}

.retention-event-filter-panel {
  width: 100%;
  min-width: 0;
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid #edf0f5;
}

.retention-config-label {
  padding: 0;
  color: #6b7280;
  font-size: 12px;
  line-height: 20px;
}

.retention-advanced-options {
  width: 100%;
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;
}

.retention-option-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 9px;
  color: #505968;
  font-size: 12px;
}

.retention-option-title {
  color: #4e5969;
  line-height: 20px;
}

.retention-option-description {
  margin-top: 4px;
  color: #667085;
  line-height: 20px;
}

.retention-option-flow {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(120px, 1fr) auto 104px;
  align-items: center;
  gap: 8px;
}

.retention-option-flow.has-metric-field {
  grid-template-columns: minmax(100px, 1fr) auto 104px minmax(100px, 1fr);
}

.retention-property-flow {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(100px, 1fr) auto;
  align-items: center;
  gap: 6px;
  line-height: 24px;
}

.builder-icon-button {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #505968;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.builder-icon-button:hover {
  background: #eef3ff;
  color: #2f6bff;
}

.builder-icon-button.danger:hover {
  background: #fff1f0;
  color: #f04438;
}

.group-row :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.sql-editor-time-range-picker :deep(.date-expression-trigger) {
  width: 100%;
  min-width: 0;
  justify-content: flex-start;
}

.metric-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.metric-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.metric-index {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: #171d4f;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}

.metric-body {
  min-width: 0;
}

.metric-title {
  margin-bottom: 8px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.metric-title-input {
  width: min(288px, 100%);
  margin-bottom: 8px;
}

.metric-title-input :deep(.el-input__wrapper),
.formula-metric-title-input :deep(.el-input__wrapper) {
  min-height: 24px;
  padding: 0 8px;
  box-shadow: none;
  background: #f7f8fb;
  border: 1px solid transparent;
  border-radius: 6px;
}

.metric-title-input :deep(.el-input__wrapper:hover),
.metric-title-input :deep(.el-input__wrapper.is-focus),
.formula-metric-title-input :deep(.el-input__wrapper:hover),
.formula-metric-title-input :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  border-color: #2f6bff;
  box-shadow: none;
}

.metric-title-input :deep(.el-input__inner),
.formula-metric-title-input :deep(.el-input__inner) {
  height: 22px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
}

.metric-chip-row {
  display: grid;
  grid-template-columns: minmax(220px, 320px) 18px 104px 24px;
  column-gap: 8px;
  row-gap: 8px;
  align-items: center;
  min-height: 30px;
}

.metric-chip-row.has-metric-field {
  grid-template-columns: minmax(180px, 240px) 18px 104px minmax(112px, 180px) 24px;
}

.metric-chip-row.calculated-metric-row {
  grid-template-columns: 28px 72px 28px minmax(100px, 1fr) 24px;
}

.formula-metric-list {
  margin-top: 10px;
}

.formula-metric-item {
  border-top: 1px solid #edf0f7;
  padding-top: 10px;
}

.formula-metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
  margin-bottom: 6px;
}

.formula-metric-title-wrap {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.formula-metric-title-input {
  width: min(220px, 100%);
  flex: 0 1 220px;
}

.formula-metric-title {
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.formula-decimal-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 7px;
  background: #f4f6fb;
  color: #1f2329;
  font-size: 12px;
  white-space: nowrap;
}

.formula-metric-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.formula-icon-button {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #7b8190;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}

.formula-icon-button:hover {
  background: #eef3ff;
  color: #2f6bff;
}

.formula-icon-button.danger:hover {
  background: #fff0f0;
  color: #f56c6c;
}

.metric-chip-row :deep(.builder-field-picker-trigger) {
  width: 100%;
  max-width: none;
}

.metric-of {
  color: #8f959e;
  font-size: 12px;
  text-align: center;
}

.metric-field-select,
.metric-aggregation {
  width: 100%;
}

.formula-entry-button {
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
}

.calculated-decimal {
  width: 100%;
}

.formula-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
  max-width: 100%;
}

.formula-display {
  display: flex;
  width: 100%;
  box-sizing: border-box;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 32px;
  padding: 7px 10px;
  border-radius: 6px;
  background: #fff;
  color: #1f2329;
  font-size: 13px;
  line-height: 18px;
  word-break: break-word;
  outline: none;
  cursor: text;
}

.formula-display.is-empty {
  color: #a8abb2;
}

.formula-display.is-invalid {
  background: #fff7f7;
}

.formula-error {
  color: #f56c6c;
  font-size: 12px;
  line-height: 18px;
}

.formula-toolbar {
  max-width: 100%;
}

.formula-toolbar-panel {
  display: inline-flex;
  flex-direction: column;
  gap: 8px;
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 0 0 12px 12px;
  background: #fff;
  box-shadow: 0 14px 32px rgba(31, 35, 41, 0.12);
}

.formula-keyboard-layout {
  display: grid;
  grid-template-columns: 90px 64px 116px;
  gap: 22px;
  align-items: start;
}

.formula-number-pad {
  display: grid;
  grid-template-columns: repeat(3, 26px);
  gap: 6px;
}

.formula-operator-pad {
  display: grid;
  grid-template-columns: repeat(2, 26px);
  gap: 6px;
}

.formula-command-panel {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  justify-items: stretch;
  gap: 2px;
  min-width: 116px;
}

.formula-metric-select {
  width: 88px;
}

.formula-placeholder {
  color: #a8abb2;
  pointer-events: none;
}

.formula-token {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0;
  border-radius: 6px;
  background: transparent;
  color: #1f2329;
  cursor: pointer;
  user-select: none;
  gap: 4px;
}

.formula-token-stack {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: 100%;
}

.formula-token-flow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.formula-token-atomicMetric,
.formula-token-metric {
  color: #1f3a8a;
}

.formula-token-operator,
.formula-token-paren {
  padding: 2px 7px;
  background: #f5f7fb;
  color: #2f3542;
  font-weight: 700;
}

.formula-token-number {
  padding: 2px 7px;
  background: #f2f5fb;
  color: #1f3a8a;
}

.formula-atomic-event,
.formula-atomic-metric {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 7px;
  background: #f4f6fb;
  color: #1f2329;
  font-size: 12px;
  line-height: 18px;
}

.formula-token-editor-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}

.formula-token-editor-row :deep(.builder-field-picker-trigger) {
  width: 160px;
  max-width: 180px;
  background: #f4f6fb;
}

.formula-token-aggregation {
  width: 88px;
}

.formula-token-filter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 7px;
  background: #f4f6fb;
  color: #7b8190;
  cursor: pointer;
}

.formula-token-filter-tree {
  margin: 0 0 2px;
}

.formula-token-of {
  color: #8f959e;
  font-size: 12px;
}

.formula-insert-target {
  width: 10px;
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 10px;
  border-radius: 4px;
  cursor: text;
}

.formula-insert-target:hover {
  background: #eef3ff;
}

.formula-insert-target.is-active {
  background: transparent;
}

.formula-cursor {
  width: 1px;
  height: 20px;
  background: #2f6bff;
  animation: formula-cursor-blink 1s step-end infinite;
}

@keyframes formula-cursor-blink {
  50% {
    opacity: 0;
  }
}

.formula-key-button {
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: #f2f5fb;
  color: #171d4f;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}

.formula-key-button:hover,
.formula-action-button:hover {
  background: #e8efff;
  color: #2f6bff;
}

.formula-number-key:last-child {
  grid-column: span 2;
  width: auto;
}

.formula-delete-key {
  grid-column: span 2;
  width: auto;
  text-align: center;
}

.formula-action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 30px;
  min-width: 116px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: #f2f5fb;
  color: #171d4f;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.formula-shortcut-hint {
  color: #b8beca;
  font-size: 12px;
  line-height: 16px;
  text-align: center;
}

.formula-shortcut-hint + .formula-action-button {
  margin-top: 8px;
}

.builder-add-link {
  height: 24px;
  padding: 0 6px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #2f6bff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.builder-add-link:hover {
  background: #eef3ff;
}

.builder-inline-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 9px;
}

.property-metric-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-metric-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.property-metric-index {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: #f5f6fa;
  color: #8f959e;
  font-size: 12px;
}

.property-metric-body {
  flex: 1 1 auto;
  min-width: 0;
}

.property-metric-editor {
  width: 100%;
  min-width: 0;
  padding: 5px 0 7px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: background-color 0.16s ease;
}

.property-metric-editor:hover,
.property-metric-editor:focus-within,
.property-metric-editor.is-active {
  background: #f7f8fa;
}

.property-metric-alias-row,
.property-metric-main-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
}

.property-metric-main-row {
  min-height: 28px;
  gap: 12px;
}

.property-metric-main-row :deep(.builder-field-picker) {
  flex: 1 1 auto;
  min-width: 0;
}

.property-metric-alias-input {
  width: min(260px, 100%);
}

.property-metric-alias-input :deep(.ed-input__wrapper),
.property-metric-alias-input :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.property-metric-alias-input :deep(.ed-input__wrapper:hover),
.property-metric-alias-input :deep(.ed-input__wrapper.is-focus),
.property-metric-alias-input :deep(.el-input__wrapper:hover),
.property-metric-alias-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 -1px 0 #2f6bff;
}

.property-metric-alias-text {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  color: #303133;
  font-size: 13px;
}

.property-metric-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.property-aggregation-select {
  flex: 0 0 104px;
}

.property-group-mode-select {
  width: 72px;
  margin: 0 2px;
}

.property-group-empty {
  padding: 18px 0 4px;
}

.property-audience-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-audience-group {
  padding: 10px 12px 8px;
  border: 1px solid rgba(31, 35, 41, 0.08);
  border-radius: 6px;
  background: #f8f9fb;
}

.property-audience-head {
  display: flex;
  align-items: center;
  min-height: 26px;
  gap: 6px;
}

.property-audience-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e8efff;
  color: #2f6bff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: 0 0 auto;
}

.property-audience-name {
  flex: 1;
  min-width: 0;
  color: #303133;
  font-size: 13px;
  font-weight: 600;
}

.property-audience-name-input {
  flex: 1;
  min-width: 0;
}

.property-audience-edit,
.property-audience-delete {
  flex: 0 0 auto;
}

.property-audience-all-users {
  margin: 8px 0 2px 26px;
  color: #646a73;
  font-size: 12px;
}

.property-audience-filter-tree {
  margin: 8px 0 0 26px;
}

.heatmap-comparison-section {
  margin-top: 16px;
  border-top: 1px solid rgba(31, 35, 41, 0.08);
  padding-top: 12px;
}

.heatmap-comparison-head {
  margin-bottom: 8px;
}

.heatmap-comparison-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.heatmap-comparison-group {
  padding: 10px 12px 8px;
  border: 1px solid rgba(31, 35, 41, 0.08);
  border-radius: 6px;
  background: #f8f9fb;
}

.heatmap-comparison-group-head {
  display: flex;
  align-items: center;
  min-height: 26px;
  gap: 6px;
}

.property-audience-actions {
  margin: 4px 0 0 26px;
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

@media (max-width: 760px) {
  .property-metric-row {
    align-items: flex-start;
  }

  .property-metric-main-row {
    flex-wrap: wrap;
    gap: 6px 8px;
  }

  .property-metric-main-row .metric-of {
    display: none;
  }

  .property-metric-main-row :deep(.builder-field-picker) {
    flex: 1 1 calc(100% - 112px);
  }

  .property-aggregation-select {
    flex: 0 0 104px;
  }

  .property-metric-actions {
    margin-left: auto;
  }

  .property-metric-alias-input {
    width: 100%;
  }
}

.group-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 26px 26px;
  gap: 6px;
  align-items: center;
}

.property-group-settings-button {
  color: #606a80;
}

.property-group-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.property-group-settings-title {
  font-size: 13px;
  font-weight: 600;
  color: #30343b;
}

.property-group-time-grain-select {
  width: 120px;
}

.group-index {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: #f5f6fa;
  color: #8f959e;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.builder-empty {
  padding: 4px 0 2px;
  color: #8f959e;
  font-size: 12px;
}

.builder-bottom-bar {
  flex: 0 0 44px;
  height: 44px;
  padding: 7px 22px;
  border-top: 1px solid rgba(31, 35, 41, 0.08);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.builder-bottom-options {
  display: flex;
  gap: 12px;
  align-items: center;
}

.sql-detail-pane {
  flex: 1;
  min-height: 0;
  padding: 12px;
  display: flex;
}

.sql-detail-pane :deep(.el-textarea),
.sql-detail-pane :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 100% !important;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 12px;
  line-height: 19px;
}

.sql-builder-panel :deep(.el-input__wrapper),
.sql-builder-panel :deep(.el-select__wrapper) {
  min-height: 26px;
  font-size: 12px;
  border-radius: 6px;
}

.sql-builder-panel :deep(.el-input__inner),
.sql-builder-panel :deep(.el-select__placeholder),
.sql-builder-panel :deep(.el-select__selected-item) {
  font-size: 12px;
}

.mcp-editor-panel {
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(47, 107, 255, 0.18);
  border-radius: 6px;
  background: #f8fbff;
}

.mcp-editor-panel :deep(.ed-form-item:last-child),
.mcp-editor-panel :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.mcp-tool-description {
  margin: -4px 0 14px;
  color: #646a73;
  font-size: 12px;
  line-height: 18px;
}

.mcp-schema-details {
  margin: -4px 0 14px;
  color: #646a73;
  font-size: 12px;
}

.mcp-schema-details summary {
  cursor: pointer;
  color: #2f6bff;
  line-height: 20px;
}

.mcp-schema-details pre {
  max-height: 180px;
  overflow: auto;
  margin: 8px 0 0;
  padding: 8px 10px;
  border-radius: 4px;
  background: #fff;
  color: #1f2329;
  font-size: 12px;
  line-height: 18px;
  white-space: pre-wrap;
  word-break: break-word;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.insight-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 6px;
}

.forecast-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 6px;
}

.forecast-config-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: center;
  column-gap: 12px;
  min-height: 32px;
}

.forecast-config-caption {
  color: #1f2329;
  font-size: 13px;
  font-weight: 500;
}

.forecast-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 12px;
}

.insight-config-row {
  display: grid;
  grid-template-columns: 72px 92px minmax(0, 1fr);
  align-items: center;
  column-gap: 12px;
  min-height: 32px;
}

.insight-config-caption {
  color: #1f2329;
  font-size: 13px;
  line-height: 20px;
}

.insight-metric-select {
  width: 100%;
}

.pivot-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 6px 0 8px;
}

.pivot-config-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 32px;
}

.pivot-config-caption {
  color: #1f2329;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
}

.pivot-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.pivot-group-values-form-item {
  margin-bottom: 4px;
}

.pivot-group-checkbox {
  margin-top: -8px;
}

:global(.pivot-group-values-select-popper .ed-select-dropdown__item:first-child),
:global(.pivot-group-values-select-popper .el-select-dropdown__item:first-child),
:global(.pivot-group-values-select-popper .ed-select-dropdown__item:nth-child(2)),
:global(.pivot-group-values-select-popper .el-select-dropdown__item:nth-child(2)) {
  color: var(--ed-color-primary, #2f6bff);
  font-weight: 600;
}

:global(.pivot-group-values-select-popper .pivot-group-values-action-option.is-selected::after),
:global(.pivot-group-values-select-popper .pivot-group-values-action-option.selected::after) {
  display: none;
}

:global(.pivot-group-values-select-popper .pivot-group-values-action-option:nth-child(2)) {
  border-bottom: 1px solid rgba(31, 35, 41, 0.08);
  margin-bottom: 4px;
}

.preview-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  margin: 18px 0 8px;
}

.chart-preview {
  height: 300px;
  border: 1px solid #dee0e3;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
}

.empty-preview {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8f959e;
}

.data-preview-table {
  width: 100%;
}

.heatmap-config-grid {
  display: grid;
  grid-template-columns: 92px minmax(180px, 1fr);
  gap: 14px 12px;
  align-items: center;
}

.heatmap-config-grid :deep(.builder-field-picker-trigger),
.heatmap-config-grid :deep(.el-input),
.heatmap-config-grid :deep(.el-select) {
  width: 100%;
}

.heatmap-event-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.heatmap-event-config {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.heatmap-event-row :deep(.builder-field-picker-trigger) {
  width: 50%;
  flex: 0 1 50%;
}

.heatmap-metric-row,
.heatmap-axis-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.heatmap-axis-row {
  display: grid;
  grid-template-columns: auto minmax(116px, 1fr) auto minmax(116px, 1fr);
  gap: 8px;
  width: 100%;
}

.heatmap-metric-row > span,
.heatmap-axis-row > span {
  flex: none;
  color: #646a73;
  font-size: 12px;
  white-space: nowrap;
}

.heatmap-metric-row :deep(.builder-field-picker),
.heatmap-metric-row :deep(.el-select) {
  min-width: 0;
  flex: 1;
}

.heatmap-axis-row :deep(.builder-field-picker) {
  min-width: 0;
  width: 100%;
}

.heatmap-aggregation-select {
  width: 110px !important;
  flex: none !important;
}

.heatmap-map-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.heatmap-map-picker :deep(.el-input) {
  flex: 1;
}

.heatmap-map-file-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #646a73;
  font-size: 12px;
}

.heatmap-map-file-empty {
  color: #8f959e;
  font-size: 12px;
}

:deep(.heatmap-map-dialog) {
  border-radius: 14px;
  overflow: hidden;
}

:deep(.heatmap-map-dialog .el-dialog__body) {
  padding: 10px 32px 24px;
}

.heatmap-map-stepper {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 2px 0 24px;
}

.heatmap-map-step {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #8f959e;
  font-size: 14px;
  white-space: nowrap;
  flex: 1;
}

.heatmap-map-step:not(:last-child)::after {
  content: '';
  height: 1px;
  background: #e5e6eb;
  flex: 1;
  margin: 0 14px;
}

.heatmap-map-step.active,
.heatmap-map-step.done {
  color: #1f2329;
}

.heatmap-map-step-index {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f1f2f5;
  color: #646a73;
  flex: none;
}

.heatmap-map-step.active .heatmap-map-step-index {
  background: #4355f5;
  color: #fff;
}

.heatmap-map-step.done .heatmap-map-step-index {
  background: #eef0ff;
  color: #4355f5;
}

.heatmap-map-upload-step,
.heatmap-map-coordinate-step,
.heatmap-map-confirm-step {
  min-height: 280px;
}

.heatmap-map-upload-step {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(180px, .72fr);
  gap: 28px;
}

.heatmap-map-uploader :deep(.el-upload-dragger) {
  height: 280px;
  border-radius: 8px;
  border-color: #d9dce5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.heatmap-map-upload-icon {
  color: #3478f6;
  font-size: 56px;
  margin-bottom: 12px;
}

.heatmap-map-upload-text {
  color: #1f2329;
  font-size: 14px;
}

.heatmap-map-upload-text span {
  color: #4355f5;
  margin-left: 4px;
}

.heatmap-map-upload-tip,
.heatmap-map-recent-empty {
  color: #8f959e;
  font-size: 12px;
  line-height: 20px;
  margin-top: 8px;
  text-align: center;
}

.heatmap-map-recent-title {
  color: #646a73;
  font-size: 13px;
  margin: 8px 0 12px;
}

.heatmap-map-recent-item {
  background: transparent;
  border: 0;
  color: #1f2329;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  text-align: left;
  width: 100%;
}

.heatmap-map-recent-item img {
  background: #20213f;
  border-radius: 6px;
  height: 220px;
  object-fit: contain;
  width: 100%;
}

.heatmap-map-coordinate-step {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(180px, .72fr);
  gap: 28px;
}

.heatmap-map-coordinate-preview,
.heatmap-map-confirm-preview {
  align-items: center;
  background: #20213f;
  border-radius: 8px;
  display: flex;
  justify-content: center;
  min-height: 280px;
  overflow: hidden;
  position: relative;
}

.heatmap-map-coordinate-preview img {
  max-height: 250px;
  max-width: 88%;
  object-fit: contain;
}

.heatmap-map-preview-empty {
  color: #fff;
  font-size: 13px;
}

.heatmap-map-corner {
  align-items: center;
  background: #ff7a00;
  border: 2px solid #fff;
  border-radius: 50%;
  color: #fff;
  display: inline-flex;
  font-size: 12px;
  height: 22px;
  justify-content: center;
  position: absolute;
  width: 22px;
}

.corner-left-bottom { bottom: 8px; left: 8px; }
.corner-right-top { right: 8px; top: 8px; }

.heatmap-map-coordinate-form {
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding-top: 6px;
}

.heatmap-map-coordinate-group {
  display: grid;
  gap: 8px;
}

.heatmap-map-coordinate-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 2px;
}

.heatmap-map-coordinate-title span {
  align-items: center;
  background: #ff7a00;
  border-radius: 50%;
  color: #fff;
  display: inline-flex;
  font-size: 12px;
  height: 20px;
  justify-content: center;
  margin-right: 6px;
  width: 20px;
}

.heatmap-map-confirm-step {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(180px, .72fr);
  gap: 28px;
}

.heatmap-map-confirm-preview img {
  max-height: 250px;
  max-width: 88%;
  object-fit: contain;
}

.heatmap-map-confirm-info {
  display: grid;
  align-content: center;
  gap: 22px;
}

.heatmap-map-confirm-info div {
  display: grid;
  gap: 5px;
}

.heatmap-map-confirm-info span {
  color: #8f959e;
  font-size: 12px;
}

.heatmap-map-confirm-info strong {
  color: #1f2329;
  font-size: 14px;
  font-weight: 400;
}

@media (max-width: 640px) {
  .heatmap-map-upload-step,
  .heatmap-map-coordinate-step,
  .heatmap-map-confirm-step {
    grid-template-columns: 1fr;
  }

  .heatmap-map-step {
    gap: 5px;
    font-size: 12px;
  }

  .heatmap-map-step:not(:last-child)::after {
    margin: 0 6px;
  }

  .heatmap-axis-row {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .heatmap-axis-row > span:nth-of-type(2) {
    grid-column: 1;
  }

  .heatmap-axis-row :deep(.builder-field-picker:nth-of-type(2)) {
    grid-column: 2;
  }
}

</style>

