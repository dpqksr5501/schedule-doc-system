# -*- coding: utf-8 -*-
"""
Update app.js with:
1. Clickable event items on A4 paper (Daily, Weekly, Monthly) -> triggers editEvent(id)
2. Color chip picker binding (Green, Blue, Black, Red)
3. Support for 'important' attendee (Red #cc0000)
"""

with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update setupModal to handle color-chip-btn instead of attendee-opt
old_modal_setup = """    document.querySelectorAll('.attendee-opt').forEach(opt => {
      opt.addEventListener('click', () => {
        document.querySelectorAll('.attendee-opt').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
        const val = opt.dataset.val;
        document.getElementById('inputAttendeeVal').value = val;
      });
    });"""

new_modal_setup = """    // 🎨 대형 컬러 칩 버튼 클릭 이벤트
    document.querySelectorAll('.color-chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.color-chip-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        const val = btn.dataset.val;
        document.getElementById('inputAttendeeVal').value = val;
      });
    });"""

if old_modal_setup in code:
    code = code.replace(old_modal_setup, new_modal_setup)

# 2. Update selectAttendeeOption
old_select_att = """  function selectAttendeeOption(val) {
    document.getElementById('inputAttendeeVal').value = val;
    document.querySelectorAll('.attendee-opt').forEach(o => {
      if (o.dataset.val === val) o.classList.add('selected');
      else o.classList.remove('selected');
    });
  }"""

new_select_att = """  function selectAttendeeOption(val) {
    document.getElementById('inputAttendeeVal').value = val;
    document.querySelectorAll('.color-chip-btn').forEach(o => {
      if (o.dataset.val === val) o.classList.add('selected');
      else o.classList.remove('selected');
    });
  }"""

if old_select_att in code:
    code = code.replace(old_select_att, new_select_att)

# 3. Update renderDaily items to be clickable
old_daily_item = """        <div class="daily-item">
          <span class="daily-item-bullet">▶</span>
          <span class="daily-item-time">${ev.time}</span>
          <span class="daily-item-title">${escapeHtml(ev.title)}</span>
          <span class="daily-item-place">&lt; ${escapeHtml(ev.place || '')} &gt;</span>
        </div>"""

new_daily_item = """        <div class="daily-item clickable-item" onclick="window.editEvent('${ev.id}')" title="마우스로 클릭하면 색상 및 내용을 바로 수정합니다">
          <span class="daily-item-bullet">▶</span>
          <span class="daily-item-time">${ev.time}</span>
          <span class="daily-item-title">${escapeHtml(ev.title)}</span>
          <span class="daily-item-place">&lt; ${escapeHtml(ev.place || '')} &gt;</span>
        </div>"""

if old_daily_item in code:
    code = code.replace(old_daily_item, new_daily_item)

# 4. Update renderWeekly rows to be clickable and support red
old_weekly_row = """            <tr>
              ${idx === 0 ? `<td class="col-date" rowspan="${rowSpan}">${day.dayLabel}</td>` : ''}
              <td class="col-time ${colorClass}">${ev.time}</td>
              <td class="col-title ${colorClass}">${escapeHtml(ev.title)}</td>
              <td class="col-place ${colorClass}">${escapeHtml(ev.place || '')}</td>
              <td class="col-dept ${colorClass}">${escapeHtml(ev.dept || '')}</td>
            </tr>"""

new_weekly_row = """            <tr class="clickable-item" onclick="window.editEvent('${ev.id}')" title="마우스로 클릭하면 색상 및 내용을 바로 수정합니다">
              ${idx === 0 ? `<td class="col-date" rowspan="${rowSpan}" onclick="event.stopPropagation()">${day.dayLabel}</td>` : ''}
              <td class="col-time ${colorClass}">${ev.time}</td>
              <td class="col-title ${colorClass}">${escapeHtml(ev.title)}</td>
              <td class="col-place ${colorClass}">${escapeHtml(ev.place || '')}</td>
              <td class="col-dept ${colorClass}">${escapeHtml(ev.dept || '')}</td>
            </tr>"""

if old_weekly_row in code:
    code = code.replace(old_weekly_row, new_weekly_row)

# 5. Color class calculation in renderWeekly
old_color_calc = "const colorClass = ev.attendee === 'gunsu' ? 'color-gunsu' : (ev.attendee === 'v_gunsu' ? 'color-vgunsu' : 'color-general');"
new_color_calc = "const colorClass = ev.attendee === 'gunsu' ? 'color-gunsu' : (ev.attendee === 'v_gunsu' ? 'color-vgunsu' : (ev.attendee === 'important' ? 'color-important' : 'color-general'));"
if old_color_calc in code:
    code = code.replace(old_color_calc, new_color_calc)

# 6. Monthly color calculation and clickable
old_monthly_item = """                  <div class="monthly-event-item" style="color: ${color};">
                    <span class="monthly-event-time">${ev.time}</span>
                    <span>${escapeHtml(ev.title)}${placePart}</span>
                  </div>"""

new_monthly_item = """                  <div class="monthly-event-item clickable-item" onclick="window.editEvent('${ev.id}')" style="color: ${color};" title="마우스로 클릭하면 색상 및 내용 바로 수정">
                    <span class="monthly-event-time">${ev.time}</span>
                    <span>${escapeHtml(ev.title)}${placePart}</span>
                  </div>"""

if old_monthly_item in code:
    code = code.replace(old_monthly_item, new_monthly_item)

old_monthly_color = "const color = ev.attendee === 'gunsu' ? '#008000' : (ev.attendee === 'v_gunsu' ? '#0000ff' : '#000000');"
new_monthly_color = "const color = ev.attendee === 'gunsu' ? '#008000' : (ev.attendee === 'v_gunsu' ? '#0000ff' : (ev.attendee === 'important' ? '#cc0000' : '#000000'));"
if old_monthly_color in code:
    code = code.replace(old_monthly_color, new_monthly_color)

# 7. Quick input support for red / important
old_quick_att = """    if (textRem.includes('부군수')) {
      attendee = 'v_gunsu';
    } else if (textRem.includes('일반') || textRem.includes('자체')) {
      attendee = 'general';
    }"""

new_quick_att = """    if (textRem.includes('부군수') || textRem.includes('파랑')) {
      attendee = 'v_gunsu';
    } else if (textRem.includes('중요') || textRem.includes('빨강') || textRem.includes('긴급')) {
      attendee = 'important';
    } else if (textRem.includes('일반') || textRem.includes('자체') || textRem.includes('검정')) {
      attendee = 'general';
    }"""

if old_quick_att in code:
    code = code.replace(old_quick_att, new_quick_att)

# 8. Admin badge support for important
old_admin_badge = """      if (ev.attendee === 'gunsu') badgeHtml = `<span class="attendee-badge badge-gunsu">🟢 ${settings.leaderTitle}</span>`;
      else if (ev.attendee === 'v_gunsu') badgeHtml = `<span class="attendee-badge badge-vgunsu">🔵 ${settings.subLeaderTitle}</span>`;
      else badgeHtml = `<span class="attendee-badge badge-general">⚫ 일반</span>`;"""

new_admin_badge = """      if (ev.attendee === 'gunsu') badgeHtml = `<span class="attendee-badge badge-gunsu">🟢 ${settings.leaderTitle}</span>`;
      else if (ev.attendee === 'v_gunsu') badgeHtml = `<span class="attendee-badge badge-vgunsu">🔵 ${settings.subLeaderTitle}</span>`;
      else if (ev.attendee === 'important') badgeHtml = `<span class="attendee-badge badge-important">🔴 중요</span>`;
      else badgeHtml = `<span class="attendee-badge badge-general">⚫ 일반</span>`;"""

if old_admin_badge in code:
    code = code.replace(old_admin_badge, new_admin_badge)

with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
    f.write(code)

print("SUCCESS: app.js updated with clickable items and direct color palette!")
