package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

data class PendingPaperSignal(
    val symbol: String,
    val direction: Int,
    val signalTime: Instant
)

data class PaperOutcome(
    val symbol: String,
    val direction: Int,
    val signalTime: Instant,
    val entryTime: Instant,
    val entryPrice: Double,
    val exitPrice: Double,
    val returnPercent: Double
)

data class DailyPaperSummary(
    val date: LocalDate,
    val averageReturnPercent: Double,
    val successPercent: Double,
    val closedSignals: Int
)

object PaperOutcomeLogic {
    private val zone = ZoneId.of("Asia/Kolkata")

    /** Score one completed signal on exactly the next 15-minute candle, entered at its open and exited at its close. */
    fun scoreNextCandle(pending: PendingPaperSignal, next: Candle): PaperOutcome? {
        if (pending.direction !in setOf(-1, 1) || !PaperStrategy.validCandle(next)) return null
        if (pending.signalTime.atZone(zone).toLocalTime() >= LocalTime.of(15, 15)) return null
        if (next.timestamp != pending.signalTime.plusSeconds(900)) return null
        if (next.timestamp.atZone(zone).toLocalDate() != pending.signalTime.atZone(zone).toLocalDate()) return null
        val percent = pending.direction * ((next.close - next.open) / next.open) * 100.0
        if (!percent.isFinite()) return null
        return PaperOutcome(
            symbol = pending.symbol,
            direction = pending.direction,
            signalTime = pending.signalTime,
            entryTime = next.timestamp,
            entryPrice = next.open,
            exitPrice = next.close,
            returnPercent = percent
        )
    }

    fun pendingFrom(row: ScanRow): PendingPaperSignal? {
        val direction = when (row.signal) {
            "PAPER_BUY" -> 1
            "PAPER_SELL" -> -1
            else -> return null
        }
        val time = row.candle?.timestamp ?: return null
        if (time.atZone(zone).toLocalTime() >= LocalTime.of(15, 15)) return null
        return PendingPaperSignal(row.symbol, direction, time)
    }

    fun summarize(outcomes: List<PaperOutcome>, firstDate: LocalDate, lastDate: LocalDate): List<DailyPaperSummary> {
        val grouped = outcomes.filter {
            val date = it.signalTime.atZone(zone).toLocalDate()
            date in firstDate..lastDate && it.returnPercent.isFinite()
        }.groupBy { it.signalTime.atZone(zone).toLocalDate() }
        return generateSequence(firstDate) { it.plusDays(1) }.takeWhile { it <= lastDate }.map { date ->
            val day = grouped[date].orEmpty()
            DailyPaperSummary(
                date = date,
                averageReturnPercent = day.map { it.returnPercent }.average().takeIf { day.isNotEmpty() } ?: 0.0,
                successPercent = day.count { it.returnPercent > 0.0 }.toDouble() * 100.0 / day.size.coerceAtLeast(1),
                closedSignals = day.size
            )
        }.toList()
    }
}
