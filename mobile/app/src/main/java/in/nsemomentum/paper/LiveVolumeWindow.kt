package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant

/** Cumulative feed-counter differences, never LTQ sums or whole-session volume comparisons. */
data class VolumePoint(val at: Instant, val total: Long)
class LiveVolumeWindow {
    private val points=java.util.ArrayDeque<VolumePoint>()
    private var epoch: Long? = null
    fun clear() { points.clear();epoch=null }
    fun add(at: Instant, total: Long, connection: Long) {
        if (epoch == connection && points.lastOrNull()?.let { at <= it.at } == true) return
        if (total < 0) { clear(); return }
        if (epoch != connection || points.lastOrNull()?.let { at.atZone(MarketSession.ZONE).toLocalDate() != it.at.atZone(MarketSession.ZONE).toLocalDate() || total < it.total } == true) points.clear()
        epoch=connection
        val last=points.lastOrNull()
        if (last != null && at <= last.at) return
        points.addLast(VolumePoint(at,total))
        while (points.size > 1 && points.first.at < at.minusSeconds(185)) points.removeFirst()
    }
    fun point(at: Instant): VolumePoint? = points.lastOrNull { it.at <= at }?.takeIf { Duration.between(it.at,at).toMillis() in 0..2000 }
    fun amount(start: Instant,end: Instant): Long? {
        if (end <= start) return null
        val first=point(start) ?: return null; val last=point(end) ?: return null
        val selected=points.filter { it.at >= first.at && it.at <= last.at }
        if (selected.zipWithNext().any { (a,b) -> Duration.between(a.at,b.at).toMillis() > 5000 || b.total < a.total }) return null
        return (last.total-first.total).takeIf { it >= 0 }
    }
}
