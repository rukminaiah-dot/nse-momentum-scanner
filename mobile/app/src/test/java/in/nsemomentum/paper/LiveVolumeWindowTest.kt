package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class LiveVolumeWindowTest {
    private val start=Instant.parse("2026-10-30T05:00:00Z")
    @Test fun comparesEqualElapsedWindowsAndIgnoresDuplicateSnapshots() {
        val w=LiveVolumeWindow()
        for(i in 0L..120L) {
            val total=if(i<=60) 1000+i*10 else 1600+(i-60)*20
            w.add(start.plusSeconds(i),total,1)
            w.add(start.plusSeconds(i),total,1)
        }
        assertEquals(600L,w.amount(start,start.plusSeconds(60))!!)
        assertEquals(1200L,w.amount(start.plusSeconds(60),start.plusSeconds(120))!!)
    }
    @Test fun resetReconnectMissingBoundaryAndDataGapsCannotInventVolume() {
        val w=LiveVolumeWindow()
        w.add(start,100,1);w.add(start.plusSeconds(60),200,1)
        assertNull(w.amount(start,start.plusSeconds(60)))
        w.add(start.plusSeconds(61),210,2)
        assertNull(w.point(start.plusSeconds(60)))
        w.add(start.plusSeconds(62),10,2)
        assertNull(w.point(start.plusSeconds(61)))
        assertNull(w.point(start.plusSeconds(65)))
    }
}
