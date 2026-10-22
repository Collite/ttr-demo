// Executes the emitted winback SQL against a small, independent DuckDB fixture.
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.tatrman.ttrp.conform.JdbcStatements;

class WinbackSqlProbe {
    public static void main(String[] args) throws Exception {
        var asOf = LocalDateTime.parse("2026-11-02T00:00:00");
        var bindings = Map.<String, Object>of(
            "as_of", asOf, "quiet_months", 12, "active_orders", 4,
            "as_of_minus_quiet_months_months", asOf.minusMonths(12),
            "as_of_minus_quiet_months_months_minus_12_months", asOf.minusMonths(24),
            "as_of_minus_mail_window_days", asOf.minusDays(92));
        try (var db = DriverManager.getConnection("jdbc:duckdb:")) {
            var s = db.createStatement();
            s.execute("CREATE TABLE income_band(sk INT, lower_bound INT)");
            s.execute("INSERT INTO income_band VALUES (1,0),(2,100),(3,200),(4,300)");
            s.execute("CREATE TABLE household_demographics(sk INT, income_band INT)");
            s.execute("INSERT INTO household_demographics VALUES (11,1),(12,3),(13,4),(14,4),(15,4)");
            s.execute("CREATE TABLE customer(sk INT, hdemo INT)");
            s.execute("INSERT INTO customer VALUES (1,11),(2,12),(3,13),(4,14),(5,15)");
            s.execute("CREATE TABLE \"order\"(order_number INT, customer INT, placed_date TIMESTAMP)");
            s.execute("INSERT INTO \"order\" SELECT c*10+i,c,TIMESTAMP '2025-06-01' FROM range(1,6) c(c),range(1,5) i(i)");
            s.execute("INSERT INTO \"order\" VALUES (100,5,TIMESTAMP '2026-10-01')");
            s.execute("CREATE TABLE winback_mail(customer INT, mailed_at TIMESTAMP, quarter TEXT, offer TEXT, run TEXT)");
            s.execute("INSERT INTO winback_mail VALUES (4,TIMESTAMP '2026-10-01','2026Q4','premium','old-run')");
            for (var route : new String[]{"premium", "standard"}) {
                var sql = Files.readString(Path.of(args[0], "islands/offer." + route + ".sql"));
                var positional = JdbcStatements.INSTANCE.positional(sql);
                try (var ps = db.prepareStatement(positional.getFirst())) {
                    int i = 1;
                    for (var name : positional.getSecond()) ps.setObject(i++, bindings.get(name));
                    var actual = new TreeSet<Integer>();
                    try (var rows = ps.executeQuery()) {
                        while (rows.next()) actual.add(rows.getInt("sk"));
                    }
                    var expected = route.equals("premium") ? Set.of(2, 3) : Set.of(1);
                    if (!actual.equals(expected)) throw new AssertionError(route + ": " + actual + " != " + expected);
                    System.out.println(route + "=" + actual);
                }
            }
        }
    }
}
