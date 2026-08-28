<template>
  <div class="practice-view">
    <!-- 头部 -->
    <div class="prv-header">
      <div class="prv-title-row">
        <h2><el-icon><Notebook /></el-icon> 我的练习</h2>
        <div class="prv-actions">
          <el-button size="small" @click="refresh">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
          <el-button size="small" @click="$router.push('/')">
            <el-icon><Back /></el-icon> 返回聊天
          </el-button>
        </div>
      </div>
      <p class="prv-sub">记录每天学了什么推进路径，收藏题目与笔记、回顾错题，见证连续学习天数。</p>
    </div>

    <div v-loading="pathLoading" class="prv-body">
      <!-- 空状态：无已确认路径 -->
      <div v-if="!pathLoading && !path" class="prv-empty">
        <el-icon :size="56" color="#c7d2fe"><Notebook /></el-icon>
        <h3>还没有学习路径</h3>
        <p>去聊天里发起「学习路径规划」，确认一份专属学习路径后，就能在这里刷题打卡了</p>
        <el-button type="primary" @click="$router.push('/')">去发起路径规划</el-button>
      </div>

      <template v-else-if="path">
        <!-- 内容快捷入口：点开在右侧开大框展示（错题集 / 我的题目 / 我的笔记） -->
        <div class="prv-quick-entry">
          <div class="prv-entry" @click="openDrawer('wrong')">
            <span class="prv-entry-ico">📕</span>
            <span class="prv-entry-name">错题集</span>
            <span class="prv-entry-count">{{ wrongTotal }} 道</span>
          </div>
          <div class="prv-entry" @click="openDrawer('collections')">
            <span class="prv-entry-ico">📂</span>
            <span class="prv-entry-name">我的题目</span>
            <span class="prv-entry-count">{{ collectionTotal }} 题</span>
          </div>
          <div class="prv-entry" @click="openDrawer('notes')">
            <span class="prv-entry-ico">🗒️</span>
            <span class="prv-entry-name">我的笔记</span>
            <span class="prv-entry-count">{{ notes.length }} 条</span>
          </div>
        </div>

        <!-- ═══════ 顶部：已确认的学习路径 ═══════ -->
        <div class="prv-card">
          <div class="prv-card-head">
            <div>
              <div class="prv-path-name">{{ path.path_name || '学习路径' }}</div>
              <div v-if="path.goal" class="prv-path-goal">{{ path.goal }}</div>
            </div>
            <el-tag :type="pathProgressTag" effect="light">{{ pathStatusText }}</el-tag>
          </div>

          <!-- 路径级推荐视频（规划时按科目 B站播放量最高，整个路径只推一个，点击直达） -->
          <div v-if="path.recommended_video" class="prv-rec-video">
            <span class="prv-rec-label">推荐视频</span>
            <a
              :href="path.recommended_video.url"
              target="_blank"
              rel="noopener"
              class="prv-stage-res-link"
              :title="path.recommended_video.url"
            >
              <span class="prv-stage-res-plat">{{ path.recommended_video.platform }}</span>
              <span class="prv-stage-res-title">{{ path.recommended_video.title }}</span>
              <span class="prv-stage-res-ext">↗</span>
            </a>
          </div>

          <!-- 路径进度条 -->
          <div class="prv-path-progress" v-if="pathProgress">
            <el-progress
              :percentage="pathProgress.progress_percent || 0"
              :stroke-width="10"
              :color="pathBarColor"
            />
            <span class="prv-path-progress-text">
              已完成 {{ pathProgress.completed_tasks }}/{{ pathProgress.total_tasks }} 个学习任务 ·
              已过 {{ pathProgress.elapsed_days }}/{{ pathProgress.total_days }} 天
              <span v-if="pathProgress.remaining_tasks > 0">· 还剩 {{ pathProgress.remaining_tasks }} 个任务</span>
            </span>
          </div>

          <!-- 阶段（宏观：月计划） -->
          <div v-if="path.stages?.length" class="prv-stages">
            <div class="prv-sec-label">阶段计划</div>
            <div class="prv-stage-list">
              <div v-for="(st, i) in path.stages" :key="st.stage || i" class="prv-stage">
                <div class="prv-stage-line">
                  <span class="prv-stage-dot">{{ st.stage || i + 1 }}</span>
                  <span v-if="i < path.stages.length - 1" class="prv-stage-conn"></span>
                </div>
                <div class="prv-stage-body">
                  <div class="prv-stage-title">{{ st.title }}</div>
                  <div v-if="st.description" class="prv-stage-desc">{{ st.description }}</div>
                  <div v-if="st.focus_points?.length" class="prv-tags">
                    <el-tag v-for="f in st.focus_points" :key="f" size="small" effect="plain">{{ f }}</el-tag>
                  </div>
                  <!-- 阶段配套资源（标准模板：视频/练习网站/数据集，点击直达） -->
                  <div v-if="st.resources?.length" class="prv-stage-res">
                    <a
                      v-for="r in st.resources"
                      :key="r.url + r.title"
                      :href="r.url"
                      target="_blank"
                      rel="noopener"
                      class="prv-stage-res-link"
                      :title="r.url"
                    >
                      <span class="prv-stage-res-plat">{{ r.platform }}</span>
                      <span class="prv-stage-res-title">{{ r.title }}</span>
                      <span class="prv-stage-res-ext">↗</span>
                    </a>
                  </div>
                  <div v-if="st.practice_cards?.length" class="prv-stage-cards">
                    <a
                      v-for="c in st.practice_cards"
                      :key="c.card_id"
                      :href="c.link"
                      target="_blank"
                      rel="noopener"
                      class="prv-stage-card-link"
                    >
                      {{ c.platform }} · {{ c.title || c.knowledge_point }}
                    </a>
                  </div>
                  <span v-if="st.estimated_days" class="prv-stage-days">约 {{ st.estimated_days }} 天</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 非编程科目：没有官方 OJ 题库，只提示一次（不再每个节点重复） -->
          <div v-if="!isProgramming && path.nodes?.length" class="prv-no-oj-tip">
            本科目没有官方 OJ 题库，直接用课本/真题练习即可。
          </div>

          <!-- 节点（学习路径各阶段的学习记录） -->
          <div v-if="path.nodes?.length" class="prv-nodes">
            <div v-for="node in path.nodes" :key="node.node_id" class="prv-node">
              <div class="prv-node-head">
                <div class="prv-node-title">
                  <span class="prv-node-badge">{{ node.node_id }}</span>
                  {{ node.title }}
                </div>
                <span v-if="node.estimated_days" class="prv-node-days">{{ node.estimated_days }} 天</span>
              </div>
              <div v-if="node.description" class="prv-node-desc">{{ node.description }}</div>

              <!-- 学习记录：用户每天写下学了什么，打钩完成（对应学习路径节点） -->
              <div class="prv-daily-log">
                <div class="prv-daily-log-head">
                  <span class="prv-daily-log-label">学习记录</span>
                  <span v-if="node.daily_logs?.length" class="prv-daily-log-count">
                    已打钩 {{ node.daily_logs.filter(l => l.done).length }} / {{ node.daily_logs.length }}
                  </span>
                  <el-button size="small" text type="primary" @click="openAddLog(node)">+ 记录今天</el-button>
                </div>

                <!-- 行内新增记录 -->
                <div v-if="addingLogNode?.node_id === node.node_id" class="prv-log-add">
                  <el-date-picker
                    v-model="newLogDate"
                    type="date"
                    value-format="YYYY-MM-DD"
                    placeholder="今天"
                    class="prv-log-date"
                  />
                  <el-input
                    v-model="newLogContent"
                    size="small"
                    placeholder="今天学了什么？如：掌握了 VLOOKUP 精确匹配…"
                    @keyup.enter="doAddLog(node)"
                  />
                  <el-button size="small" type="primary" :loading="savingLog" @click="doAddLog(node)">保存</el-button>
                  <el-button size="small" text @click="closeAddLog">取消</el-button>
                </div>

                <div v-if="node.daily_logs?.length" class="prv-log-list">
                  <div v-for="log in node.daily_logs" :key="log.id" class="prv-log-item" :class="{ done: log.done }">
                    <span class="prv-log-date">{{ fmtDate(log.date) }}</span>
                    <span class="prv-log-content">{{ log.content }}</span>
                    <el-button
                      size="small"
                      text
                      :type="log.done ? 'success' : 'primary'"
                      class="prv-log-toggle"
                      @click="toggleLog(node, log)"
                    >{{ log.done ? '✓ 已学' : '打钩' }}</el-button>
                    <el-button size="small" text type="danger" class="prv-log-del" @click="deleteLog(node, log)">×</el-button>
                  </div>
                </div>
                <div v-else-if="addingLogNode?.node_id !== node.node_id" class="prv-log-empty">
                  还没有记录，点「+ 记录今天」写下今天学了什么吧
                </div>
              </div>

              <!-- 学习资源：B站/文档链接，点开即跳转；看完推进当日学习记录打钩 -->
              <div class="prv-node-res">
                <div class="prv-node-res-head">
                  <span class="prv-node-res-label">学习资源</span>
                  <el-button size="small" text type="primary" @click="openAddRes(node)">+ 添加</el-button>
                </div>
                <div v-if="node.resources?.length" class="prv-res-list">
                  <div v-for="r in node.resources" :key="r.rid" class="prv-res-item" :class="{ watched: r.watched }">
                    <a class="prv-res-link" :href="r.url" target="_blank" rel="noopener" :title="r.url">
                      <span v-if="r.platform" class="prv-res-plat">{{ r.platform }}</span>
                      <span class="prv-res-title">{{ r.title }}</span>
                    </a>
                    <span v-if="r.watched" class="prv-res-watched">✓ 已看完</span>
                    <el-button v-else size="small" text type="success" class="prv-res-watch-btn" @click="openWatch(r)">看完了</el-button>
                    <el-button size="small" text type="danger" class="prv-res-del" @click="onDeleteRes(r)">×</el-button>
                  </div>
                </div>
                <div v-else class="prv-res-empty">这个知识点还没有学习资源，点「+ 添加」挂一个 B站课程/文档链接，下次直接点开学。</div>
              </div>

              <!-- 跳过：这个节点我会了 -->
              <div class="prv-node-study">
                <el-button size="small" plain class="prv-node-skip-btn" @click="onSkipNode(node)">
                  ⏭ 这个我会了，跳过
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══════ 中部：进度追踪 + 激励 ═══════ -->
        <div class="prv-grid">
          <!-- 统计卡片 -->
          <div class="prv-card prv-stats">
            <div class="prv-sec-label">进度追踪</div>
            <div class="prv-stats-row">
              <div class="prv-stat">
                <el-progress
                  type="circle"
                  :percentage="progress?.progress_percent || 0"
                  :width="92"
                  :color="'#6366f1'"
                >
                  <template #default>
                    <div class="prv-stat-big">{{ progress?.progress_percent || 0 }}%</div>
                  </template>
                </el-progress>
                <div class="prv-stat-label">练习完成</div>
                <div class="prv-stat-sub">{{ progress?.done || 0 }}/{{ progress?.total_cards || 0 }} 题</div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num" :class="{ warn: (progress?.total_accuracy_percent || 0) < 60 }">
                  {{ progress?.total_accuracy_percent || 0 }}%
                </div>
                <div class="prv-stat-label">正确率 <span class="prv-stat-mini">OJ+AI</span></div>
                <div class="prv-stat-sub">
                  {{ progress?.total_correct || 0 }} 对 / {{ progress?.total_answered || 0 }} 答
                </div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num hot">🔥 {{ progress?.streak?.current || 0 }}</div>
                <div class="prv-stat-label">连续打卡</div>
                <div class="prv-stat-sub">最长 {{ progress?.streak?.longest || 0 }} 天</div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num">{{ progress?.total_checkins || 0 }}</div>
                <div class="prv-stat-label">累计打卡</div>
                <div class="prv-stat-sub">今天要打卡吗？</div>
              </div>
            </div>
            <div class="prv-checkin-row">
              <el-button type="primary" round :disabled="checkedToday" @click="openCheckin">
                <el-icon><Calendar /></el-icon>
                {{ checkedToday ? '今日已打卡 ✓' : '今日打卡' }}
              </el-button>
              <el-button v-if="wrongTotal > 0" round type="warning" plain @click="openDrawer('wrong')">
                <el-icon><Warning /></el-icon> {{ wrongTotal }} 道错题待回顾
              </el-button>
            </div>
            <!-- AI 出题练习统计（任何科目都有效，非编程科目 OJ 卡被清零但 AI 统计存活） -->
            <div v-if="(progress?.ai_total || 0) > 0" class="prv-ai-bar">
              🧠 AI 练习：共 {{ progress.ai_total }} 题 · 对 {{ progress.ai_correct }} · 错 {{ progress.ai_wrong }} · 正确率 {{ progress.ai_accuracy_percent }}%
            </div>
          </div>

          <!-- 最近打卡 -->
          <div class="prv-card">
            <div class="prv-sec-label">打卡记录</div>
            <div v-if="progress?.checkins?.length" class="prv-checkin-list">
              <div v-for="c in recentCheckins" :key="c.date" class="prv-checkin-item">
                <span class="prv-checkin-date">{{ c.date }}</span>
                <span class="prv-checkin-node">{{ nodeTitle(c.node_id) }}</span>
                <span v-if="c.note" class="prv-checkin-note">{{ c.note }}</span>
              </div>
            </div>
            <div v-else class="prv-empty-small">还没有打卡记录，学完今天的内容就打个卡吧！</div>
          </div>
        </div>

        <!-- ═══════ 下部：最近练习回顾 ═══════ -->
        <div class="prv-card">
          <div class="prv-sec-label">最近练习</div>
          <div v-if="progress?.recent?.length" class="prv-recent-list">
            <div v-for="r in progress.recent.slice(0, 10)" :key="r.card_id" class="prv-recent-item">
              <span class="prv-recent-status" :class="'st-' + r.status">{{ statusText(r.status) }}</span>
              <span class="prv-recent-title">{{ r.title }}</span>
              <span class="prv-recent-time">{{ shortTime(r.updated_at) }}</span>
            </div>
          </div>
          <div v-else class="prv-empty-small">还没有练习记录，做完题后（如聊天里答题、收藏题目）会出现在这里。</div>
        </div>
      </template>
    </div>

    <!-- 新建题目集弹窗 -->
    <el-dialog v-model="createCollectionVisible" title="📁 新建题目集" width="380px" append-to-body>
      <el-input v-model="newColName" placeholder="题目集名称，如：SQL 错题" maxlength="30" @keyup.enter="onCreateCol" />
      <template #footer>
        <el-button @click="createCollectionVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newColName.trim()" :loading="savingCol" @click="onCreateCol">创建</el-button>
      </template>
    </el-dialog>

    <!-- 资源「看完了」自评弹窗 -->
    <el-dialog v-model="watchDialogVisible" title="✓ 标记看完了" width="420px" append-to-body>
      <div class="prv-dialog-tip">
        在 <b>{{ watchRes?.platform || '平台' }}</b> 看完了「{{ watchRes?.title || '' }}」？
        写一句学到了什么，路径进度会随之前移（我只能记录你点开的是哪个链接 + 你的自评，追踪不到视频具体哪一集）。
      </div>
      <el-input
        v-model="watchNote"
        type="textarea"
        :rows="3"
        placeholder="学到了什么？比如：掌握了 SQL 的 GROUP BY…"
      />
      <template #footer>
        <el-button @click="watchDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingWatch" @click="doWatch">确认看完</el-button>
      </template>
    </el-dialog>

    <!-- 添加学习资源弹窗 -->
    <el-dialog v-model="addResDialogVisible" title="➕ 添加学习资源" width="460px" append-to-body>
      <div class="prv-dialog-tip">给「{{ addResNode?.title || '' }}」挂一个学习资源（B站课程、博客、文档等），下次点链接直接跳转：</div>
      <div class="prv-addres-search">
        <el-button size="small" plain type="primary" @click="openVideoSearch">搜B站热门</el-button>
        <span class="prv-addres-search-tip">搜播放量/点赞最高的视频自动填入，或直接自定义填写</span>
      </div>
      <el-form label-width="64px" class="prv-study-form">
        <el-form-item label="平台">
          <el-select v-model="addResForm.platform" style="width:100%">
            <el-option v-for="p in RES_PLATFORMS" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="addResForm.title" placeholder="如：B站《SQL入门到进阶》第1-5集" />
        </el-form-item>
        <el-form-item label="链接">
          <el-input v-model="addResForm.url" placeholder="https://www.bilibili.com/video/…" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addResDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingRes" @click="doAddRes">添加</el-button>
      </template>
    </el-dialog>

    <!-- 打卡弹窗 -->
    <el-dialog v-model="checkinVisible" title="🔥 今日打卡" width="420px" append-to-body>
      <div class="prv-dialog-tip">选择今天完成学习的节点（可留空），写一句学习心得吧</div>
      <el-select v-model="checkinNode" placeholder="选择节点（可选）" clearable style="width:100%;margin-bottom:10px">
        <el-option v-for="n in path?.nodes || []" :key="n.node_id" :label="n.title" :value="n.node_id" />
      </el-select>
      <el-input
        v-model="checkinNote"
        type="textarea"
        :rows="3"
        placeholder="今天学到了什么？比如：掌握了前缀和…"
      />
      <template #footer>
        <el-button @click="checkinVisible = false">取消</el-button>
        <el-button type="primary" :loading="checking" @click="doCheckin">确认打卡</el-button>
      </template>
    </el-dialog>

    <!-- 搜B站热门视频（选用后回填资源表单） -->
    <VideoSearchDialog
      v-model="videoSearchVisible"
      :initial-keyword="addResNode?.title || ''"
      @select="onVideoSelected"
    />

    <!-- 右侧大框展示：错题集 / 我的题目 / 我的笔记（点击顶部快捷入口打开，左边栏不动） -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerTitle"
      size="72%"
      append-to-body
      class="prv-drawer"
    >
      <div class="prv-drawer-body">
        <!-- 错题集（OJ 错题 + AI 错题，全量不截断） -->
        <template v-if="drawerType === 'wrong'">
          <div v-if="!wrongOj.length && !wrongAi.length" class="prv-empty-small">太棒了，目前没有错题</div>

          <!-- OJ 错题：跳官方平台重做 -->
          <div v-if="wrongOj.length" class="prv-sub-sec">
            <div class="prv-sub-label">OJ 错题 <span class="prv-stat-mini">({{ wrongOj.length }} 道)</span></div>
            <div class="prv-mistake-list">
              <div v-for="c in wrongOj" :key="c.card_id" class="prv-mistake-item" :id="'wrong-' + c.card_id">
                <div class="prv-mistake-head">
                  <span class="pc-platform" :style="{ color: platformColor(c.platform) }">{{ c.platform }}</span>
                  <span v-if="c.problem_no" class="prv-mistake-no">{{ c.problem_no }}</span>
                  <a v-if="c.link" :href="c.link" target="_blank" rel="noopener" class="prv-mistake-link">重做 →</a>
                  <el-button size="small" text type="danger" class="prv-mistake-remove" @click="onRemoveWrong('oj', c.card_id)">移除</el-button>
                </div>
                <div class="prv-mistake-title">{{ c.title }}</div>
                <div v-if="c.knowledge_point" class="prv-mistake-note">知识点：{{ c.knowledge_point }}</div>
                <div v-if="c.note" class="prv-mistake-note">{{ c.note }}</div>
              </div>
            </div>
          </div>

          <!-- AI 错题：页内重做（做对即移出错题集） -->
          <div v-if="wrongAi.length" class="prv-sub-sec">
            <div class="prv-sub-label">AI 错题 <span class="prv-stat-mini">({{ wrongAi.length }} 道，页内重做)</span></div>
            <div class="prv-ai-wrong-list">
              <div v-for="rec in wrongAi" :key="rec.exercise_id + '-' + rec.updated_at" class="prv-ai-wrong-item">
                <div class="prv-ai-wrong-topic">{{ rec.topic || 'AI 练习' }}</div>
                <ExerciseCard
                  :exercise="aiToCard(rec)"
                  :current-index="0"
                  :total-exercises="1"
                  standalone
                  @answer="(e) => onRedoAi(rec, e)"
                />
                <div class="prv-ai-wrong-ops">
                  <el-button size="small" text type="primary" @click="toggleAiAns(rec)">
                    {{ showAiAns[rec.exercise_id] ? '收起解析' : '查看解析' }}
                  </el-button>
                  <el-button size="small" text type="danger" @click="onRemoveWrong('ai', rec.exercise_id)">移除</el-button>
                </div>
                <div v-if="showAiAns[rec.exercise_id]" class="prv-ai-wrong-ans">
                  <div class="prv-ai-wrong-ans-line"><b>正确答案：</b>{{ rec.answer }}</div>
                  <div v-if="rec.explanation" class="prv-ai-wrong-ans-line"><b>解析：</b>{{ rec.explanation }}</div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 我的题目：命名题目集（收藏 AI 出的题） -->
        <template v-else-if="drawerType === 'collections'">
          <div class="prv-collections-head">
            <div class="prv-collections-title">📂 我的题目 <span class="prv-stat-mini">({{ collectionTotal }} 题)</span></div>
            <el-button size="small" type="primary" plain @click="openCreateCol">
              <el-icon><Plus /></el-icon> 新建题目集
            </el-button>
          </div>

          <div v-if="!collections.length" class="prv-empty-small prv-collections-empty">
            在聊天答题时点「📥 加入错题集」，把题目收进你的题目集，随时回来重做巩固。
          </div>

          <div v-for="col in collections" :key="col.collection_id" class="prv-col">
            <div
              class="prv-col-head"
              :class="{ active: expandedCol === col.collection_id }"
              @click="expandedCol = expandedCol === col.collection_id ? '' : col.collection_id"
            >
              <div class="prv-col-title">
                <span class="prv-col-arrow">{{ expandedCol === col.collection_id ? '▾' : '▸' }}</span>
                <span class="prv-col-name">📁 {{ col.name }}</span>
                <span class="prv-col-count">{{ col.questions.length }} 题</span>
                <span
                  v-for="t in colTypeBadges(col)"
                  :key="t.label"
                  class="prv-col-type-chip"
                  :style="{ background: t.color }"
                >{{ t.label }}</span>
              </div>
              <el-dropdown trigger="click" @command="cmd => onColCommand(cmd, col)" @click.stop>
                <el-button size="small" text type="primary" @click.stop>
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="delete">🗑️ 删除题目集</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div v-if="expandedCol === col.collection_id" class="prv-col-body">
              <div v-if="!col.questions.length" class="prv-empty-small">
                这个题目集还是空的，去聊天答题时点「加入错题集」收题吧。
              </div>
              <div v-for="q in col.questions" :key="q.qid" class="prv-col-q">
                <ExerciseCard
                  :exercise="colQToCard(q)"
                  :current-index="0"
                  :total-exercises="1"
                  standalone
                  @answer="e => onRedoCol(col, q, e)"
                />
                <div class="prv-col-q-ops">
                  <el-button size="small" text type="danger" @click="onRemoveQ(col, q)">移除</el-button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 我的笔记：保存的思维导图图片 -->
        <template v-else-if="drawerType === 'notes'">
          <div class="prv-notes-head">
            <div class="prv-notes-title">🗒️ 我的笔记 <span class="prv-stat-mini">({{ notes.length }})</span></div>
          </div>

          <div v-if="!notes.length" class="prv-empty-small">还没有保存笔记。在资源查看页生成思维导图后点「保存」，就会归到这里。</div>

          <div v-else class="prv-note-grid">
            <div v-for="n in notes" :key="n.note_id" class="prv-note">
              <el-image :src="noteImg(n)" :preview-src-list="[noteImg(n)]" fit="contain" lazy class="prv-note-img" />
              <div class="prv-note-info">
                <div class="prv-note-title">{{ n.title }}</div>
                <div class="prv-note-ops">
                  <a :href="noteImg(n)" target="_blank" rel="noopener" class="prv-note-download">下载</a>
                  <el-button size="small" text type="danger" @click="onDeleteNote(n)">删除</el-button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { ElMessage, ElMessageBox } from 'element-plus'
import ExerciseCard from '@/components/ExerciseCard.vue'
import VideoSearchDialog from '@/components/VideoSearchDialog.vue'
import { Notebook, Refresh, Back, Calendar, Warning, Plus, MoreFilled } from '@element-plus/icons-vue'
import { onlinePathApi, practiceApi } from '@/api'

const router = useRouter()
const chatStore = useChatStore()

const path = ref(null)
const progress = ref(null)
const pathLoading = ref(true)
const refreshing = ref(false)
// 是否编程/CS 科目——非编程科目（物理/化学等）隐藏「去官方找题」（牛客/LeetCode 上没有物理题）
const isProgramming = ref(true)
// 错题集（全量）：OJ 错题 + AI 错题（来自 GET /practice/wrong-questions，不截断）
const wrongOj = ref([])
const wrongAi = ref([])
// 我的题目（命名题目集）
const collections = ref([])
const expandedCol = ref('')
const createCollectionVisible = ref(false)
const newColName = ref('')
const savingCol = ref(false)
// 我的笔记（保存的思维导图图片）
const notes = ref([])
// 右侧大框展示（抽屉）：错题集 / 我的题目 / 我的笔记
const drawerVisible = ref(false)
const drawerType = ref('wrong')
const drawerTitle = computed(() => ({
  wrong: '错题集',
  collections: '我的题目',
  notes: '我的笔记',
}[drawerType.value] || ''))
function openDrawer(type) {
  drawerType.value = type
  drawerVisible.value = true
}
// 学习记录（日计划）：用户自由记录每天学了什么 + 打钩
const addingLogNode = ref(null)
const newLogDate = ref('')
const newLogContent = ref('')
const savingLog = ref(false)

let pathProgress = ref(null)

const pathStatusText = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: '进度正常', behind: '进度落后', ahead: '进度超前' }[s] || ''
})
const pathProgressTag = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: 'success', behind: 'danger', ahead: 'warning' }[s] || 'info'
})
const pathBarColor = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: '#10b981', behind: '#ef4444', ahead: '#f59e0b' }[s] || '#6366f1'
})

const checkedToday = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return progress.value?.checkins?.some(c => c.date === today) || false
})

const recentCheckins = computed(() => (progress.value?.checkins || []).slice(-8).reverse())

const wrongTotal = computed(() => wrongOj.value.length + wrongAi.value.length)

/** AI 错题记录 → ExerciseCard 所需的题目结构 */
function aiToCard(rec) {
  return {
    id: '复习',
    type: rec.type || 'choice',
    question: rec.question,
    options: rec.options || [],
    answer: rec.answer,
    explanation: rec.explanation,
    difficulty: rec.difficulty,
    topic: rec.topic,
  }
}

/** AI 错题重做：服务端判对错；做对移出错题集，做错保留可再试 */
async function onRedoAi(rec, e) {
  try {
    const res = await practiceApi.redoAiExercise(chatStore.userId, rec.exercise_id, e.userAnswer)
    if (res.ok) {
      if (res.correct) ElMessage.success('回答正确！已移出错题集')
      else ElMessage.warning('还是不对，看下解析想清楚后再试一次吧')
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`重做保存失败: ${err.message}`)
  }
}

// ==================== 错题集：解析 / 移除 ====================

/** 哪些 AI 错题展开了解析（key: exercise_id） */
const showAiAns = ref({})

function toggleAiAns(rec) {
  showAiAns.value = { ...showAiAns.value, [rec.exercise_id]: !showAiAns.value[rec.exercise_id] }
}

/** 只刷新错题集（OJ + AI） */
async function loadWrong() {
  try {
    const res = await practiceApi.wrongQuestions(chatStore.userId)
    wrongOj.value = res?.oj || []
    wrongAi.value = res?.ai || []
  } catch (e) {
    console.error('加载错题集失败', e)
  }
}

/** 错题集移除：AI 删记录 / OJ 置 done 移出错题集 */
async function onRemoveWrong(kind, targetId) {
  try {
    await ElMessageBox.confirm('确定从错题集移除这道题吗？', '移除错题', { type: 'warning' })
    const res = await practiceApi.wrongRemove(chatStore.userId, kind, targetId)
    if (res.ok) {
      ElMessage.success('已移出错题集')
      await loadWrong()
    }
  } catch (e) { /* 取消 */ }
}

// ==================== 我的题目（命名题目集） ====================

const collectionTotal = computed(() => collections.value.reduce((s, c) => s + (c.questions?.length || 0), 0))

/** 集合内题型汇总 chips（如：选择 3 / 填空 1） */
function colTypeBadges(col) {
  const count = {}
  for (const q of col.questions || []) {
    const label = { choice: '选择', fill: '填空', judge: '判断', essay: '简答', application: '应用' }[q.type] || q.type
    count[label] = (count[label] || 0) + 1
  }
  const colors = { 选择: '#6366f1', 填空: '#10b981', 判断: '#f59e0b', 简答: '#ec4899', 应用: '#8b5cf6' }
  return Object.entries(count).map(([label, n]) => ({ label: `${label} ${n}`, color: colors[label] || '#6b7280' }))
}

/** 集合内题目记录 → ExerciseCard 所需的题目结构 */
function colQToCard(q) {
  return {
    id: '收藏',
    type: q.type || 'choice',
    question: q.question,
    options: q.options || [],
    answer: q.answer,
    explanation: q.explanation,
    difficulty: q.difficulty,
    topic: q.topic,
  }
}

async function loadCollections() {
  try {
    const res = await practiceApi.listCollections(chatStore.userId)
    collections.value = res?.collections || []
  } catch (e) {
    console.error('加载题目集失败', e)
  }
}

function openCreateCol() {
  newColName.value = ''
  createCollectionVisible.value = true
}

async function onCreateCol() {
  const name = newColName.value.trim()
  if (!name) return
  savingCol.value = true
  try {
    const res = await practiceApi.createCollection(chatStore.userId, name)
    if (res.ok) {
      ElMessage.success('题目集已创建')
      createCollectionVisible.value = false
      newColName.value = ''
      await loadCollections()
    } else {
      ElMessage.warning(res.detail || '创建失败，可能已存在同名题目集')
    }
  } catch (e) {
    ElMessage.error('创建失败，请稍后重试')
  } finally {
    savingCol.value = false
  }
}

async function onDeleteCol(col) {
  try {
    await ElMessageBox.confirm(`确定删除题目集「${col.name}」吗？其中的题目会被移除。`, '删除题目集', { type: 'warning' })
    const res = await practiceApi.deleteCollection(chatStore.userId, col.collection_id)
    if (res.ok) {
      ElMessage.success('已删除')
      if (expandedCol.value === col.collection_id) expandedCol.value = ''
      await loadCollections()
    }
  } catch (e) { /* 取消 */ }
}

function onColCommand(cmd, col) {
  if (cmd === 'delete') onDeleteCol(col)
}

async function onRemoveQ(col, q) {
  try {
    await ElMessageBox.confirm('确定从题目集中移除这题吗？', '移除题目', { type: 'warning' })
    const res = await practiceApi.removeCollectionQuestion(chatStore.userId, col.collection_id, q.qid)
    if (res.ok) {
      ElMessage.success('已移除')
      await loadCollections()
    }
  } catch (e) { /* 取消 */ }
}

/** 集合内重做：服务端判对错，本地更新状态避免整页重载丢展开 */
async function onRedoCol(col, q, e) {
  try {
    const res = await practiceApi.redoCollectionQuestion(chatStore.userId, col.collection_id, q.qid, e.userAnswer)
    if (res.ok) {
      if (res.correct) ElMessage.success('回答正确！')
      else ElMessage.warning('还是不对，看下解析再想想吧')
      if (res.question) Object.assign(q, res.question)
    }
  } catch (err) {
    ElMessage.error(`保存失败: ${err.message}`)
  }
}

// ==================== 我的笔记（保存的思维导图图片） ====================

function noteImg(n) {
  return practiceApi.noteImageUrl(chatStore.userId, n.note_id)
}

async function loadNotes() {
  try {
    const res = await practiceApi.listNotes(chatStore.userId)
    notes.value = res?.notes || []
  } catch (e) {
    console.error('加载笔记失败', e)
  }
}

async function onDeleteNote(n) {
  try {
    await ElMessageBox.confirm(`确定删除笔记「${n.title}」吗？图片也会一并删除。`, '删除笔记', { type: 'warning' })
    const res = await practiceApi.deleteNote(chatStore.userId, n.note_id)
    if (res.ok) {
      ElMessage.success('已删除')
      await loadNotes()
    }
  } catch (e) { /* 取消 */ }
}

// ==================== 学习记录（日计划）：记录 + 打钩 ====================

function fmtDate(d) {
  if (!d) return '未填日期'
  const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (m) return `${Number(m[2])}/${Number(m[3])}`
  return String(d)
}

function openAddLog(node) {
  addingLogNode.value = node
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  newLogDate.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  newLogContent.value = ''
}

function closeAddLog() {
  addingLogNode.value = null
  newLogDate.value = ''
  newLogContent.value = ''
}

async function doAddLog(node) {
  if (!newLogContent.value.trim()) {
    ElMessage.warning('写一下今天学了什么吧')
    return
  }
  savingLog.value = true
  try {
    const res = await practiceApi.dailyLogAdd(chatStore.userId, node.node_id, newLogContent.value.trim(), newLogDate.value)
    if (res.ok) {
      ElMessage.success('已记录，记得学完打钩')
      closeAddLog()
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`保存失败: ${err.message}`)
  } finally {
    savingLog.value = false
  }
}

async function toggleLog(node, log) {
  try {
    await practiceApi.dailyLogUpdate(chatStore.userId, log.id, { done: !log.done })
    await refresh(true)
  } catch (err) {
    ElMessage.error(`操作失败: ${err.message}`)
  }
}

async function deleteLog(node, log) {
  try {
    await ElMessageBox.confirm(`确定删除「${log.content.slice(0, 20)}…」这条记录吗？`, '删除记录', { type: 'warning' })
    const res = await practiceApi.dailyLogDelete(chatStore.userId, log.id)
    if (res.ok) {
      ElMessage.success('已删除')
      await refresh(true)
    }
  } catch (e) { /* 取消 */ }
}

function platformColor(p) {
  return { LeetCode: '#f59e0b', 牛客: '#00a1e9', 洛谷: '#16a34a', AcWing: '#6366f1', PTA: '#dc2626' }[p] || '#6b7280'
}
function statusText(s) {
  return { undone: '未做', done: '已做', correct: '做对', wrong: '做错' }[s] || s
}
function shortTime(iso) {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' ')
}
function nodeTitle(nodeId) {
  return path.value?.nodes?.find(n => n.node_id === nodeId)?.title || nodeId
}

// 打卡
const checkinVisible = ref(false)
const checkinNode = ref('')
const checkinNote = ref('')
const checking = ref(false)

function openCheckin() {
  checkinNode.value = ''
  checkinNote.value = ''
  checkinVisible.value = true
}
async function doCheckin() {
  checking.value = true
  try {
    const res = await practiceApi.checkin(chatStore.userId, checkinNode.value || '', checkinNote.value)
    if (res.ok) {
      ElMessage.success(`打卡成功！连续 ${res.streak} 天 🔥`)
      checkinVisible.value = false
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`打卡失败: ${err.message}`)
  } finally {
    checking.value = false
  }
}

async function refresh(silent = false) {
  if (!silent) refreshing.value = true
  const [pRes, prRes, wRes, cRes, nRes] = await Promise.allSettled([
    onlinePathApi.get(chatStore.userId),
    practiceApi.progress(chatStore.userId),
    practiceApi.wrongQuestions(chatStore.userId),
    practiceApi.listCollections(chatStore.userId),
    practiceApi.listNotes(chatStore.userId),
  ])
  if (pRes.status === 'fulfilled') {
    path.value = pRes.value?.ok ? pRes.value.path : null
    pathProgress.value = pRes.value?.progress || null
    isProgramming.value = pRes.value?.is_programming !== false
  } else {
    path.value = null
  }
  if (prRes.status === 'fulfilled') progress.value = prRes.value?.progress || null
  if (wRes.status === 'fulfilled') {
    wrongOj.value = wRes.value?.oj || []
    wrongAi.value = wRes.value?.ai || []
  }
  if (cRes.status === 'fulfilled') collections.value = cRes.value?.collections || []
  if (nRes.status === 'fulfilled') notes.value = nRes.value?.notes || []
  if (!silent) {
    pathLoading.value = false
    refreshing.value = false
  }
}

// ==================== 节点学习资源（添加 / 看完自评 / 删除）+ 跳过节点 ====================

const RES_PLATFORMS = ['B站', 'YouTube', '中国大学MOOC', '知乎', '博客', '文档', '其他']
const watchDialogVisible = ref(false)
const watchRes = ref(null)
const watchNote = ref('')
const savingWatch = ref(false)
const addResDialogVisible = ref(false)
const addResNode = ref(null)
const addResForm = ref({ platform: 'B站', title: '', url: '' })
const savingRes = ref(false)

function openWatch(r) {
  watchRes.value = r
  watchNote.value = ''
  watchDialogVisible.value = true
}

async function doWatch() {
  savingWatch.value = true
  try {
    const res = await practiceApi.markResourceWatched(chatStore.userId, watchRes.value.rid, watchNote.value.trim())
    watchDialogVisible.value = false
    ElMessage.success(res.task_marked ? '已记录「看完了」，路径进度已前移 ✅' : '已记录「看完了」 ✅')
    await refresh(true)
  } catch (err) {
    ElMessage.error(`保存失败: ${err.message}`)
  } finally {
    savingWatch.value = false
  }
}

function openAddRes(node) {
  addResNode.value = node
  addResForm.value = { platform: 'B站', title: '', url: '' }
  addResDialogVisible.value = true
}

async function doAddRes() {
  if (!addResForm.value.title.trim() || !addResForm.value.url.trim()) {
    ElMessage.info('请填写资源标题和链接')
    return
  }
  savingRes.value = true
  try {
    const res = await practiceApi.addNodeResource(
      chatStore.userId, addResNode.value.node_id,
      addResForm.value.title, addResForm.value.url, addResForm.value.platform)
    if (res.ok) {
      addResDialogVisible.value = false
      ElMessage.success('已添加学习资源，确认后下次点链接直接跳转')
      await refresh(true)
    } else {
      ElMessage.warning(res.error || '添加失败，请重试')
    }
  } catch (err) {
    ElMessage.error(`添加失败: ${err.message}`)
  } finally {
    savingRes.value = false
  }
}

async function onDeleteRes(r) {
  try {
    await ElMessageBox.confirm('确定删除这条学习资源吗？', '删除资源', { type: 'warning' })
    const res = await practiceApi.deleteNodeResource(chatStore.userId, r.rid)
    if (res.ok) {
      ElMessage.success('已删除')
      await refresh(true)
    }
  } catch (e) { /* 取消 */ }
}

async function onSkipNode(node) {
  try {
    await ElMessageBox.confirm(
      `「${node.title}」这个知识点你确定已经会了吗？确认后该节点全部学习任务会被标记完成，路径自动跳到下一个知识点。`,
      '跳过该知识点',
      { type: 'warning', confirmButtonText: '确认跳过', cancelButtonText: '再想想' }
    )
    const res = await practiceApi.skipNode(chatStore.userId, node.node_id)
    if (res.ok) {
      ElMessage.success(`已跳过「${node.title}」，路径前移 ${res.marked || 0} 个任务`)
      await refresh(true)
    }
  } catch (e) { /* 取消 */ }
}

// ==================== 搜B站热门视频（添加资源时选用） ====================

const videoSearchVisible = ref(false)

function openVideoSearch() {
  videoSearchVisible.value = true
}

/** 选中搜索结果 → 回填添加资源表单（platform 固定 B站） */
function onVideoSelected(v) {
  addResForm.value = {
    platform: v.platform || 'B站',
    title: v.title,
    url: v.url,
  }
  ElMessage.success(`已填入「${(v.title || '').slice(0, 20)}…」，点「添加」即可`)
}

onMounted(() => refresh())
</script>

<style scoped>
.practice-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6fa;
}
.prv-header {
  padding: 20px 28px 0;
  flex-shrink: 0;
}
.prv-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prv-title-row h2 {
  font-size: 18px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.prv-sub { font-size: 13px; color: #9ca3af; margin-top: 4px; }
.prv-actions { display: flex; gap: 8px; }

/* 内容快捷入口：点击在右侧开大框（错题集 / 我的题目 / 我的笔记） */
.prv-quick-entry {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.prv-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 12px;
  padding: 16px 18px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.prv-entry:hover {
  border-color: #c7d2fe;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.08);
  transform: translateY(-1px);
}
.prv-entry-ico { font-size: 20px; }
.prv-entry-name { font-size: 14px; font-weight: 600; color: #1f2937; flex: 1; }
.prv-entry-count { font-size: 12px; color: #9ca3af; }
@media (max-width: 700px) { .prv-quick-entry { grid-template-columns: 1fr; } }

/* 右侧大框（抽屉）内容区 */
.prv-drawer-body { padding: 4px 6px 20px; }

.prv-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 28px 32px;
}

/* 卡片 & 布局 */
.prv-card {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.prv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) { .prv-grid { grid-template-columns: 1fr; } }

.prv-sec-label {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 12px;
  letter-spacing: 0.3px;
}

/* 空状态 */
.prv-empty {
  text-align: center;
  padding: 80px 20px;
  color: #9ca3af;
}
.prv-empty h3 { margin: 12px 0 6px; color: #374151; }
.prv-empty p { margin-bottom: 20px; font-size: 14px; max-width: 420px; margin-left: auto; margin-right: auto; }
.prv-empty-small { font-size: 13px; color: #d1d5db; padding: 8px 0; }

/* 路径卡 */
.prv-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.prv-path-name { font-size: 17px; font-weight: 700; color: #1f2937; }
.prv-path-goal { font-size: 13px; color: #6b7280; margin-top: 4px; }

.prv-path-progress {
  margin: 14px 0 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.prv-path-progress .el-progress { flex: 1; }
.prv-path-progress-text { font-size: 12px; color: #9ca3af; white-space: nowrap; }

/* 阶段时间线 */
.prv-stages { margin-top: 16px; }
.prv-stage-list { display: flex; flex-direction: column; gap: 0; }
.prv-stage { display: flex; gap: 12px; }
.prv-stage-line { display: flex; flex-direction: column; align-items: center; width: 22px; flex-shrink: 0; }
.prv-stage-dot {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.prv-stage-conn { width: 2px; flex: 1; min-height: 14px; background: #e5e7eb; }
.prv-stage-body { flex: 1; padding-bottom: 16px; }
.prv-stage-title { font-size: 14px; font-weight: 600; color: #374151; }
.prv-stage-desc { font-size: 12.5px; color: #6b7280; margin-top: 3px; line-height: 1.5; }
.prv-stage-days { font-size: 11px; color: #9ca3af; margin-top: 4px; display: inline-block; }
.prv-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.prv-stage-cards { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.prv-stage-card-link {
  font-size: 11.5px;
  color: #6366f1;
  text-decoration: none;
  border: 1px solid #e0e7ff;
  background: #eef2ff;
  border-radius: 6px;
  padding: 3px 8px;
  transition: border-color 0.15s, background 0.15s;
}
.prv-stage-card-link:hover { border-color: #6366f1; background: #e0e7ff; }

/* 阶段配套资源（标准模板：视频/练习网站/数据集，点击直达） */
.prv-stage-res {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.prv-rec-video {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.prv-rec-label {
  font-size: 12px;
  font-weight: 600;
  color: #6366f1;
  white-space: nowrap;
}
.prv-stage-res-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  text-decoration: none;
  color: #1f2937;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 8px;
  padding: 4px 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.prv-stage-res-link:hover {
  border-color: #6366f1;
  box-shadow: 0 1px 4px rgba(99, 102, 241, 0.15);
}
.prv-stage-res-plat {
  font-weight: 600;
  color: #6366f1;
}
.prv-stage-res-title {
  color: #4b5563;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}
.prv-stage-res-ext {
  font-size: 10px;
  color: #9ca3af;
}

/* 节点 */
.prv-nodes { margin-top: 16px; }
.prv-node {
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: #fbfbfd;
}
.prv-node-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.prv-node-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #374151; }
.prv-node-badge {
  font-size: 10px;
  color: #6366f1;
  background: #eef0ff;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 700;
  flex-shrink: 0;
}
.prv-node-days { font-size: 11px; color: #9ca3af; flex-shrink: 0; }
.prv-node-desc { font-size: 12.5px; color: #6b7280; margin-top: 4px; }

/* 学习记录（日计划）：用户自由记录 + 打钩 */
.prv-daily-log {
  margin-top: 10px;
  padding: 10px 12px;
  background: #fafbff;
  border: 1px solid #eef0f4;
  border-radius: 8px;
}
.prv-daily-log-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.prv-daily-log-label { font-size: 12.5px; font-weight: 600; color: #374151; }
.prv-daily-log-count { font-size: 11px; color: #9ca3af; }
.prv-log-add {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.prv-log-date { width: 150px; }
.prv-log-add .el-input { flex: 1; min-width: 200px; }
.prv-log-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.prv-log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #fff;
  border: 1px solid #f0f1f5;
  border-radius: 6px;
  font-size: 12.5px;
  color: #374151;
  transition: opacity 0.15s;
}
.prv-log-item.done {
  opacity: 0.55;
}
.prv-log-item.done .prv-log-content {
  text-decoration: line-through;
  color: #9ca3af;
}
.prv-log-date {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef0ff;
  color: #6366f1;
}
.prv-log-content { flex: 1; min-width: 0; word-break: break-all; }
.prv-log-toggle { flex-shrink: 0; font-size: 12px; }
.prv-log-del { flex-shrink: 0; font-size: 14px; }
.prv-log-empty {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
}

/* 统计 */
.prv-stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}
@media (max-width: 700px) { .prv-stats-row { grid-template-columns: repeat(2, 1fr); } }
.prv-stat { text-align: center; padding: 10px 4px; }
.prv-stat-big { font-size: 20px; font-weight: 800; color: #6366f1; }
.prv-stat-num { font-size: 26px; font-weight: 800; color: #1f2937; }
.prv-stat-num.hot { color: #f97316; }
.prv-stat-num.warn { color: #ef4444; }
.prv-stat-label { font-size: 12px; color: #6b7280; margin-top: 4px; }
.prv-stat-mini { font-size: 10px; color: #9ca3af; font-weight: 400; }
.prv-stat-sub { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.prv-checkin-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }

/* AI 练习统计条 */
.prv-ai-bar {
  margin-top: 12px;
  padding: 8px 12px;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  font-size: 12.5px;
  color: #4338ca;
  text-align: center;
}

/* 错题集分段 */
.prv-sub-sec { margin-bottom: 14px; }
.prv-sub-sec:last-child { margin-bottom: 0; }
.prv-sub-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}
.prv-ai-wrong-list { display: flex; flex-direction: column; gap: 12px; }
.prv-ai-wrong-item {
  border: 1px solid #fee2e2;
  background: #fffbfb;
  border-radius: 10px;
  padding: 10px;
}
.prv-ai-wrong-topic {
  font-size: 12px;
  color: #ef4444;
  font-weight: 600;
  margin-bottom: 8px;
}
.prv-ai-wrong-ops {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 4px;
}
.prv-ai-wrong-ans {
  margin-top: 6px;
  padding: 8px 10px;
  background: #f0f7ff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  font-size: 12.5px;
  color: #374151;
  line-height: 1.6;
}
.prv-ai-wrong-ans-line + .prv-ai-wrong-ans-line { margin-top: 4px; }
.prv-ai-wrong-ans-line b { color: #2563eb; font-weight: 600; }

/* 打卡记录 */
.prv-checkin-list { display: flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; }
.prv-checkin-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  padding: 6px 10px;
  background: #f9fafb;
  border-radius: 8px;
}
.prv-checkin-date { color: #6366f1; font-weight: 600; flex-shrink: 0; }
.prv-checkin-node { color: #374151; flex-shrink: 0; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prv-checkin-note { color: #9ca3af; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 错题本 */
.prv-mistake-list { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.prv-mistake-item {
  border: 1px solid #fee2e2;
  background: #fff5f5;
  border-radius: 8px;
  padding: 8px 10px;
}
.prv-mistake-head { display: flex; align-items: center; gap: 8px; }
.prv-mistake-no { font-size: 11px; color: #9ca3af; background: #fee2e2; padding: 1px 6px; border-radius: 4px; }
.prv-mistake-link { margin-left: auto; font-size: 12px; color: #ef4444; text-decoration: none; font-weight: 600; }
.prv-mistake-remove { flex-shrink: 0; }
.prv-mistake-title { font-size: 13px; font-weight: 600; color: #374151; margin-top: 3px; }
.prv-mistake-note { font-size: 12px; color: #6b7280; margin-top: 3px; }

/* 最近练习 */
.prv-recent-list { display: flex; flex-direction: column; max-height: 300px; overflow-y: auto; }
.prv-recent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 12.5px;
}
.prv-recent-status {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  flex-shrink: 0;
}
.st-undone { background: #eef0f4; color: #6b7280; }
.st-done { background: #dbeafe; color: #1d4ed8; }
.st-correct { background: #dcfce7; color: #166534; }
.st-wrong { background: #fee2e2; color: #b91c1c; }
.prv-recent-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #374151; }
.prv-recent-time { font-size: 11px; color: #9ca3af; flex-shrink: 0; }

.prv-dialog-tip { font-size: 12.5px; color: #6b7280; margin-bottom: 10px; }

/* 添加资源：搜B站热门入口 */
.prv-addres-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.prv-addres-search-tip { font-size: 12px; color: #9ca3af; }

/* 我的题目（题目集） */
.prv-collections-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.prv-collections-title { font-size: 13px; font-weight: 600; color: #6b7280; }
.prv-collections-empty { padding: 6px 0 2px; }
.prv-col { border: 1px solid #eef0f4; border-radius: 10px; margin-bottom: 8px; }
.prv-col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.prv-col-head:hover, .prv-col-head.active { background: #f8f9ff; }
.prv-col-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.prv-col-arrow { font-size: 11px; color: #9ca3af; }
.prv-col-name { font-size: 13.5px; font-weight: 600; color: #1f2937; }
.prv-col-count { font-size: 12px; color: #9ca3af; }
.prv-col-type-chip {
  font-size: 10px; color: #fff; padding: 1px 7px; border-radius: 8px; font-weight: 600;
}
.prv-col-body { padding: 4px 12px 12px; border-top: 1px dashed #eef0f4; }
.prv-col-q { margin-top: 12px; }
.prv-col-q-ops { display: flex; justify-content: flex-end; }

/* 我的笔记（思维导图图片） */
.prv-notes-head { margin-bottom: 10px; }
.prv-notes-title { font-size: 13px; font-weight: 600; color: #6b7280; }
.prv-note-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.prv-note {
  border: 1px solid #eef0f4;
  border-radius: 10px;
  background: #fbfbfd;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.prv-note-img {
  width: 100%;
  height: 220px;
  background: #ffffff;
  display: block;
  cursor: zoom-in;
}
.prv-note-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px dashed #eef0f4;
}
.prv-note-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.prv-note-ops {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.prv-note-download {
  font-size: 12px;
  color: #6366f1;
  text-decoration: none;
  font-weight: 500;
}
.prv-note-download:hover { color: #4f46e5; }

/* 节点跳过 */
.prv-node-study {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #eef0f4;
}

/* 通用弹窗表单（添加资源等） */
.prv-study-form { margin-top: 4px; }
.prv-study-form .el-form-item { margin-bottom: 14px; }

/* 节点学习资源 */
.prv-node-res {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #eef0f4;
}
/* 非编程科目：没有官方 OJ 题库，只在顶部提示一次 */
.prv-no-oj-tip {
  margin-top: 12px;
  font-size: 12.5px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 8px 12px;
  border-radius: 8px;
}
.prv-node-res-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.prv-node-res-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}
.prv-res-list { display: flex; flex-direction: column; gap: 6px; }
.prv-res-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  padding: 5px 10px;
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 8px;
}
.prv-res-item.watched { background: #f0fdf4; border-color: #bbf7d0; }
.prv-res-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
  color: #374151;
  flex: 1;
  min-width: 0;
}
.prv-res-link:hover { color: #6366f1; }
.prv-res-plat {
  font-size: 11px;
  color: #6366f1;
  background: #eef2ff;
  padding: 1px 6px;
  border-radius: 6px;
  flex-shrink: 0;
}
.prv-res-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prv-res-watched { font-size: 12px; color: #16a34a; flex-shrink: 0; }
.prv-res-watch-btn, .prv-res-del { flex-shrink: 0; }
.prv-res-empty { font-size: 12px; color: #d1d5db; }
.prv-node-skip-btn { flex-shrink: 0; }
</style>
