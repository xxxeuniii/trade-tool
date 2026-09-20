import React, { useEffect, useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import styles from "./styles";

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
const STATUS = [undefined, "present", "absent", "leave", "holiday"];

function keyFor(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function AttendanceCalendar({ attendance, onChange, onMonthChange, isDesktop }) {
  const today = new Date();
  const [cursor, setCursor] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const monthKey = `${year}-${String(month + 1).padStart(2, "0")}`;

  useEffect(() => {
    onMonthChange(monthKey);
  }, [monthKey]);

  function getDayRule(date, status) {
    const weekend = date.getDay() === 0 || date.getDay() === 6;
    const holiday = status === "holiday";
    return { holiday, weekend, workday: !holiday && !weekend };
  }

  const days = useMemo(() => {
    const leading = new Date(year, month, 1).getDay();
    return Array.from(
      { length: 42 },
      (_, index) => new Date(year, month, index - leading + 1)
    );
  }, [year, month]);

  const stats = useMemo(() => {
    const monthPrefix = `${year}-${String(month + 1).padStart(2, "0")}`;
    const workdayKeys = days
      .filter((date) => date.getMonth() === month && getDayRule(date, attendance?.[keyFor(date)]).workday)
      .map(keyFor);
    const entries = Object.entries(attendance || {}).filter(
      ([key]) => key.startsWith(monthPrefix) && workdayKeys.includes(key)
    );
    const present = entries.filter(([, value]) => value === "present").length;
    const leave = entries.filter(([, value]) => value === "leave").length;
    const absent = entries.filter(([, value]) => value === "absent").length;
    const expected = workdayKeys.length;
    const actual = expected - leave;
    return { present, leave, absent, expected, actual, rate: actual ? ((present / actual) * 100).toFixed(1) : "0.0" };
  }, [attendance, days, year, month]);

  function moveMonth(step) {
    setCursor(new Date(year, month + step, 1));
  }

  function cycleDay(date) {
    const key = keyFor(date);
    const currentIndex = STATUS.indexOf(attendance?.[key]);
    onChange(key, STATUS[(currentIndex + 1) % STATUS.length]);
  }

  return (
    <View style={[styles.page, isDesktop && styles.pageDesktop]}>
      <View style={styles.metrics}>
        <View style={[styles.metric, stats.leave === 0 && styles.metricFourColumn]}><Text style={styles.metricValue}>{stats.expected}</Text><Text style={styles.metricLabel}>应出勤</Text></View>
        {stats.leave > 0 && <View style={[styles.metric, styles.metricDivider]}><Text style={styles.metricValue}>{stats.actual}</Text><Text style={styles.metricLabel}>实际出勤</Text></View>}
        <View style={[styles.metric, stats.leave === 0 && styles.metricFourColumn, styles.metricDivider]}><Text style={[styles.metricValue, styles.presentText]}>{stats.present}</Text><Text style={styles.metricLabel}>WIO</Text></View>
        {stats.leave > 0 && <View style={[styles.metric, styles.metricSecondRow]}><Text style={[styles.metricValue, styles.leaveText]}>{stats.leave}</Text><Text style={styles.metricLabel}>请假</Text></View>}
        <View style={[styles.metric, stats.leave === 0 && styles.metricFourColumn, stats.leave > 0 && styles.metricSecondRow, styles.metricDivider]}><Text style={[styles.metricValue, styles.absentText]}>{stats.absent}</Text><Text style={styles.metricLabel}>WFH</Text></View>
        <View style={[styles.metric, stats.leave === 0 && styles.metricFourColumn, stats.leave > 0 && styles.metricSecondRow, styles.metricDivider]}><Text style={[styles.metricValue, styles.rateText]}>{stats.rate}%</Text><Text style={styles.metricLabel}>出勤率</Text></View>
      </View>

      <View style={styles.calendar}>
        <View style={styles.calendarHeader}>
          <Pressable onPress={() => moveMonth(-1)} style={styles.navButton}><Text style={styles.navText}>‹</Text></Pressable>
          <Text style={styles.monthTitle}>{year}.{String(month + 1).padStart(2, "0")}</Text>
          <Pressable onPress={() => moveMonth(1)} style={styles.navButton}><Text style={styles.navText}>›</Text></Pressable>
        </View>

        <View style={styles.weekRow}>
          {WEEKDAYS.map((day, index) => <Text key={day} style={[styles.weekday, (index === 0 || index === 6) && styles.weekend]}>{day}</Text>)}
        </View>
        <View style={styles.daysGrid}>
          {days.map((date, index) => {
            const key = keyFor(date);
            const savedStatus = attendance?.[key];
            const status = STATUS.includes(savedStatus) ? savedStatus : undefined;
            const isToday = key === keyFor(today);
            const isOutsideMonth = date.getMonth() !== month;
            const dayRule = getDayRule(date, status);
            const canEdit = !isOutsideMonth && !dayRule.weekend;
            const dimOutsideMonth = isOutsideMonth;
            const hasStatus = status && canEdit;
            return (
              <Pressable disabled={!canEdit} key={`${key}-${index}`} onPress={() => cycleDay(date)} style={[styles.dayCell, !hasStatus && dayRule.weekend && !dimOutsideMonth && styles.weekendCell, hasStatus && styles[`${status}Cell`], dimOutsideMonth && styles.outsideMonthCell, isToday && !isOutsideMonth && styles.todayCell]}>
                <Text style={[styles.dayNumber, !hasStatus && dayRule.weekend && !dimOutsideMonth && styles.weekendNumber, hasStatus && styles[`${status}Number`], dimOutsideMonth && styles.outsideMonthNumber]}>{date.getDate()}</Text>
                {status === "holiday" && canEdit && <Text style={[styles.dayBadge, styles.holidayBadge]}>假</Text>}
                {hasStatus && <View style={[styles.statusDot, styles[`${status}Dot`]]} />}
              </Pressable>
            );
          })}
        </View>

        <View style={styles.legend}>
          <View style={styles.legendItem}><View style={[styles.legendDot, styles.presentDot]} /><Text style={styles.legendText}>WIO</Text></View>
          <View style={styles.legendItem}><View style={[styles.legendDot, styles.absentDot]} /><Text style={styles.legendText}>WFH</Text></View>
          <View style={styles.legendItem}><View style={[styles.legendDot, styles.leaveDot]} /><Text style={styles.legendText}>请假</Text></View>
          <View style={styles.legendItem}><Text style={[styles.legendBadge, styles.holidayBadge]}>假</Text><Text style={styles.legendText}>法定假日</Text></View>
          <Text style={styles.formula}>出勤率 = WIO 工作日 /（应出勤 − 请假）</Text>
        </View>
        <View style={styles.todayButtonRow}>
          <Pressable
            onPress={() => setCursor(new Date(today.getFullYear(), today.getMonth(), 1))}
            style={({ pressed }) => [styles.todayButton, pressed && styles.todayButtonPressed]}
          >
            <Text style={styles.todayButtonText}>回到今天</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}
