// SPDX-License-Identifier: Apache-2.0
package org.tatrman.automation.runner

import io.kotest.assertions.throwables.shouldThrow
import io.kotest.core.spec.style.StringSpec
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.tatrman.automation.api.AutomationException
import org.tatrman.automation.api.ErrorCode
import org.tatrman.automation.apply.ApplyPlanner
import org.tatrman.automation.apply.ApplyRow
import org.tatrman.automation.apply.PreviewMetadata
import org.tatrman.automation.apply.PreviewPlan
import org.tatrman.automation.bundle.BundleKind
import org.tatrman.automation.bundle.BundleLoader
import org.tatrman.automation.bundle.Checkout
import org.tatrman.automation.identity.AuthorMap
import org.tatrman.automation.staging.LocalStagingStore
import org.tatrman.automation.staging.Staging
import java.math.BigDecimal
import java.nio.file.Files
import java.nio.file.Path
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/** Actual Hartland bundles and verifier; only the Query door's result tables are faked. */
class HartlandWriterPreviewSpec :
    StringSpec({
        val root = Path.of(System.getProperty("hartland.root"))
        val bundle =
            BundleLoader(AuthorMap(emptyMap())).load(
                Checkout(root, "master", "0123456789abcdef", "bora", "bora@post.cz"),
                BundleKind.SERVED,
            )
        val run = UUID.fromString("01234567-89ab-cdef-0123-456789abcdef")
        val opened = Instant.parse("2031-08-15T12:00:00.123456Z")

        suspend fun preview(
            name: String,
            asOf: Instant,
            empty: Boolean = false,
            writerOnly: Boolean = false,
        ): PreviewPlan =
            coroutineScope {
                val source = bundle.recipes.getValue(name)
                val recipe =
                    if (writerOnly) {
                        source.recipe.copy(
                            wiring =
                                source.recipe.wiring.filter {
                                    source.coverage.actions
                                        .getValue(it.action)
                                        .sinks["native"] == "writer"
                                },
                        )
                    } else {
                        source.recipe
                    }
                val loaded = source.copy(recipe = recipe, manifest = source.manifest.copy(recipe = recipe))
                loaded.coverage.refusal shouldBe null
                val metadata = PreviewMetadata(loaded.coverage.actions, bundle.entities, loaded.coverage.targets)
                val context =
                    runnerContext(loaded).copy(
                        id = run,
                        startedAt = opened,
                        previewMetadata = metadata,
                        bindings = RecipeBindings.resolve(loaded.recipe, asOf),
                    )
                val temp = Files.createTempDirectory("hartland-writer-preview-")
                var plan: PreviewPlan? = null
                val reads = AtomicInteger()
                val journals = AtomicInteger()
                val runner =
                    PartRunner(
                        context,
                        Door { read ->
                            reads.incrementAndGet()
                            val port =
                                loaded.manifest.islands
                                    .single { it.name == read.island }
                                    .outputs
                                    .single { loaded.statements[it.file] == read.sql }
                                    .port
                            val standard = port == "standard"
                            val row =
                                read.columns.map { column ->
                                    when (column.name) {
                                        "item" -> 17
                                        "warehouse" -> 3
                                        "sk" -> if (standard) 102 else 101
                                        "on_hand" -> 2
                                        "weekly_demand" -> java.math.BigDecimal("3.125")
                                        "proposed_qty" -> java.math.BigDecimal("17")
                                        "sold" -> 25.0
                                        "quarter" -> {
                                            val day = asOf.atOffset(ZoneOffset.UTC)
                                            "${day.year}-Q${(day.monthValue - 1) / 3 + 1}"
                                        }
                                        "route" -> if (name == "winback") port else "propose"
                                        "verdict_reason" -> "writer adoption fixture"
                                        "last_mailed" -> java.time.LocalDateTime.parse("2020-01-01T00:00:00")
                                        else -> 4
                                    }
                                }
                            val rows =
                                if (name == "winback" && read.island != "offer") {
                                    listOf(
                                        row,
                                        row.mapIndexed { i, v ->
                                            if (read.columns[i].name == "sk") 102 else v
                                        },
                                    )
                                } else {
                                    listOf(row)
                                }
                            ReadResult(Table(read.columns, if (empty) emptyList() else rows))
                        },
                        Staging(LocalStagingStore(temp)) {},
                        this,
                        preview = ApplyPlanner(Clock.fixed(opened.plusSeconds(86400), ZoneOffset.UTC))::preview,
                        recordPreview = { _, _, value ->
                            journals.incrementAndGet()
                            plan = value
                        },
                    )
                try {
                    runner.evaluate()
                    val initialReads = reads.get()
                    runner.evaluate() // idempotent evaluation of the same staged run
                    val replay = ApplyPlanner(Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"), ZoneOffset.UTC)).preview(runner)
                    replay.actions shouldBe plan!!.actions

                    fun withoutWrittenAt(rows: List<ApplyRow>) =
                        rows.map {
                            it.copy(row = it.row?.let { row -> JsonObject(row - "written_at") })
                        }
                    withoutWrittenAt(replay.rows) shouldBe withoutWrittenAt(plan!!.rows)
                    reads.get() shouldBe initialReads
                    journals.get() shouldBe 1
                    plan!!
                } finally {
                    runner.close()
                    temp.toFile().deleteRecursively()
                }
            }

        "all six bundles load and their approval scopes resolve in this checkout" {
            bundle.recipes.size shouldBe 6
            bundle.recipes.values.forEach { it.coverage.refusal shouldBe null }
        }

        "full H3 currently refuses its deferred nested purchasing action" {
            shouldThrow<AutomationException> {
                preview("reorder_proposals", Instant.parse("2026-04-01T00:00:00Z"))
            }.code shouldBe ErrorCode.PREVIEW_UNSUPPORTED
        }

        "H3 writer projection produces an exact bigint key and every required proposal attribute" {
            val plan = preview("reorder_proposals", Instant.parse("2026-04-01T00:00:00Z"), writerOnly = true)
            val row = plan.rows.single { it.entity == "er.entity.reorder_proposal" }
            row.key!!
                .getValue("proposal_id")
                .jsonPrimitive.long
                .let { it < 0 } shouldBe true
            row.row!!.keys shouldBe setOf("proposal_id", "run", "state", "item", "warehouse", "on_hand", "weekly_demand", "proposed_qty")
            row.row!!["proposal_id"] shouldBe row.key!!["proposal_id"]
            row.row!!["item"] shouldBe JsonPrimitive(17)
            row.row!!["warehouse"] shouldBe JsonPrimitive(3)
            row.row!!["on_hand"] shouldBe JsonPrimitive(2)
            row.row!!["run"] shouldBe JsonPrimitive(run.toString())
            row.row!!["state"] shouldBe JsonPrimitive("proposed")
            row.row!!["weekly_demand"]!!
                .jsonPrimitive.content
                .toBigDecimal() shouldBe BigDecimal("3.13")
            row.row!!["proposed_qty"]!!.jsonPrimitive.long shouldBe 17L
            plan.actions.single { it.action == "propose" }.arguments["proposal_id"] shouldBe row.key!!["proposal_id"]
        }

        "H5 quarter follows as-of while run and mailing time follow pinned Open" {
            for ((asOf, quarter) in listOf(
                "2019-02-14T12:00:00Z" to "2019-Q1",
                "2026-03-31T23:59:59Z" to "2026-Q1",
                "2026-04-01T00:00:00Z" to "2026-Q2",
                "2026-06-30T23:59:59Z" to "2026-Q2",
                "2026-07-01T00:00:00Z" to "2026-Q3",
                "2026-09-30T23:59:59Z" to "2026-Q3",
                "2026-10-01T00:00:00Z" to "2026-Q4",
                "2026-12-31T23:59:59Z" to "2026-Q4",
                "2027-01-01T00:00:00Z" to "2027-Q1",
                // Prague 2027-01-01 00:30 and US UTC-05 2026-12-31 20:00 use their UTC quarter.
                "2026-12-31T23:30:00Z" to "2026-Q4",
                "2027-01-01T01:00:00Z" to "2027-Q1",
            )) {
                val plan = preview("winback", Instant.parse(asOf))
                val rows = plan.rows.filter { it.entity == "er.entity.winback_mail" }
                rows.size shouldBe 2
                rows.map {
                    it.key!!
                        .getValue("customer")
                        .jsonPrimitive.int
                } shouldBe listOf(101, 102)
                rows.map { it.row!!["offer"] } shouldBe listOf(JsonPrimitive("premium"), JsonPrimitive("standard"))
                rows.forEach {
                    it.key!!["quarter"] shouldBe JsonPrimitive(quarter)
                    it.row!!["quarter"] shouldBe JsonPrimitive(quarter)
                    it.row!!["run"] shouldBe JsonPrimitive(run.toString())
                    it.row!!["mailed_at"] shouldBe JsonPrimitive(opened.atOffset(ZoneOffset.UTC).toString())
                }
            }
        }

        "empty H3 writer and H5 selections produce no actions" {
            for (name in listOf("reorder_proposals", "winback")) {
                preview(
                    name,
                    Instant.parse("2026-04-01T00:00:00Z"),
                    empty = true,
                    writerOnly = name == "reorder_proposals",
                ).actions shouldBe
                    emptyList()
            }
        }
    })
