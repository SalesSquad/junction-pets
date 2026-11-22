//! Deterministic development-only agent workflow fault simulator.
//! This does NOT execute Chibi agents, OCI containers, or untrusted code.
use std::env;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::thread;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Receipt {
    seed: u64,
    fault: &'static str,
    outcome: &'static str,
    attempts: u8,
    committed: bool,
    duplicate_prevented: bool,
    fingerprint: u64,
}

fn mix(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9e3779b97f4a7c15);
    x = (x ^ (x >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94d049bb133111eb);
    x ^ (x >> 31)
}

// The four synthetic fault classes are mutually exclusive by seed, and
// independent of thread scheduling. Each campaign is exactly replayable.
fn simulate(seed: u64) -> Receipt {
    let entropy = mix(seed);
    let class = entropy % 17;
    let (fault, outcome, attempts, committed, duplicate_prevented) = match class {
        0 => ("resource_denial", "denied", 1, false, false),
        1..=3 => ("process_exit", "recovered", 2, true, false),
        4..=6 => ("timeout", "recovered", 2, true, false),
        7..=8 => ("duplicate_delivery", "deduplicated", 2, true, true),
        _ => ("none", "committed", 1, true, false),
    };
    // A stable, source-defined state transition receipt, never a runtime attestation.
    let fingerprint = mix(seed
        ^ (attempts as u64)
        ^ ((committed as u64) << 9)
        ^ ((duplicate_prevented as u64) << 13)
        ^ class.rotate_left(19));
    Receipt {
        seed,
        fault,
        outcome,
        attempts,
        committed,
        duplicate_prevented,
        fingerprint,
    }
}

fn campaign(start: u64, count: usize, workers: usize) -> Vec<Receipt> {
    let workers = workers.min(count.max(1)).max(1);
    let mut groups = Vec::with_capacity(workers);
    thread::scope(|scope| {
        let mut handles = Vec::with_capacity(workers);
        for shard in 0..workers {
            handles.push(scope.spawn(move || {
                let mut local = Vec::new();
                for index in (shard..count).step_by(workers) {
                    local.push(simulate(start + index as u64));
                }
                local
            }));
        }
        for handle in handles {
            groups.extend(handle.join().expect("simulation worker panicked"));
        }
    });
    groups.sort_unstable_by_key(|row| row.seed);
    groups
}

fn write_receipts<W: Write>(out: &mut W, rows: &[Receipt]) -> io::Result<()> {
    for row in rows {
        writeln!(
            out,
            "{{\"kind\":\"scenario\",\"seed\":{},\"fault\":\"{}\",\"outcome\":\"{}\",\"attempts\":{},\"committed\":{},\"duplicate_prevented\":{},\"fingerprint\":\"{:016x}\",\"runtime_authorized\":false}}",
            row.seed,
            row.fault,
            row.outcome,
            row.attempts,
            row.committed,
            row.duplicate_prevented,
            row.fingerprint
        )?;
    }
    let committed = rows.iter().filter(|r| r.committed).count();
    let denied = rows.len() - committed;
    let recovered = rows.iter().filter(|r| r.outcome == "recovered").count();
    let duplicates = rows.iter().filter(|r| r.duplicate_prevented).count();
    let retries = rows
        .iter()
        .map(|r| (r.attempts - 1) as usize)
        .sum::<usize>();
    let checksum = rows
        .iter()
        .fold(0u64, |acc, row| mix(acc ^ row.fingerprint));
    writeln!(
        out,
        "{{\"kind\":\"summary\",\"scenarios\":{},\"committed\":{},\"denied\":{},\"recovered\":{},\"duplicate_prevented\":{},\"retries\":{},\"checksum\":\"{:016x}\",\"runtime_authorized\":false}}",
        rows.len(),
        committed,
        denied,
        recovered,
        duplicates,
        retries,
        checksum
    )
}

fn usage() -> &'static str {
    "usage: cargo run --release -- --seeds N [--start N] [--workers N] [--output FILE]\n     development-only deterministic simulator; not a qualified RML1 execution runtime"
}

fn parse_args() -> Result<(u64, usize, usize, Option<String>), String> {
    let mut start = 0u64;
    let mut seeds = 4096usize;
    let mut workers = 4usize;
    let mut output = None;
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        if flag == "--help" || flag == "-h" {
            println!("{}", usage());
            std::process::exit(0);
        }
        let val = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--start" => start = val.parse().map_err(|_| "invalid start".to_string())?,
            "--seeds" => seeds = val.parse().map_err(|_| "invalid seeds".to_string())?,
            "--workers" => workers = val.parse().map_err(|_| "invalid workers".to_string())?,
            "--output" => output = Some(val),
            _ => return Err(format!("unknown argument: {flag}")),
        }
    }
    if seeds == 0 || seeds > 65536 {
        return Err("seeds must be in 1..=65536".into());
    }
    if workers == 0 || workers > 64 {
        return Err("workers must be in 1..=64".into());
    }
    if start.checked_add(seeds as u64 - 1).is_none() {
        return Err("seed range overflow".into());
    }
    Ok((start, seeds, workers, output))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (start, seeds, workers, output) = parse_args().map_err(|reason| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("{reason}\n{}", usage()),
        )
    })?;
    let rows = campaign(start, seeds, workers);
    if let Some(path) = output {
        let mut out = BufWriter::new(File::create(path)?);
        write_receipts(&mut out, &rows)?;
        out.flush()?;
    } else {
        let mut out = BufWriter::new(io::stdout().lock());
        write_receipts(&mut out, &rows)?;
        out.flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn independent_of_worker_count() {
        assert_eq!(campaign(2, 4096, 1), campaign(2, 4096, 8));
    }
    #[test]
    fn replay_is_stable() {
        let full = campaign(100, 4096, 4);
        for row in full.iter().step_by(113) {
            assert_eq!(*row, campaign(row.seed, 1, 1)[0]);
        }
    }
    #[test]
    fn faults_are_covered_and_fail_closed() {
        let rows = campaign(0, 4096, 4);
        for fault in [
            "process_exit",
            "timeout",
            "duplicate_delivery",
            "resource_denial",
        ] {
            assert!(rows.iter().any(|r| r.fault == fault));
        }
        assert!(
            rows.iter()
                .filter(|r| r.fault == "resource_denial")
                .all(|r| !r.committed)
        );
        assert!(
            rows.iter()
                .filter(|r| r.fault == "duplicate_delivery")
                .all(|r| r.duplicate_prevented)
        );
        assert!(
            rows.iter()
                .filter(|r| r.fault == "process_exit" || r.fault == "timeout")
                .all(|r| r.committed && r.attempts == 2)
        );
    }
    #[test]
    fn receipt_summary_contains_non_authorization() {
        let mut out = Vec::new();
        write_receipts(&mut out, &campaign(1, 16, 2)).unwrap();
        let text = String::from_utf8(out).unwrap();
        assert_eq!(text.lines().count(), 17);
        assert!(
            text.lines()
                .all(|l| l.contains("\"runtime_authorized\":false"))
        );
        assert!(
            text.lines()
                .last()
                .unwrap()
                .contains("\"kind\":\"summary\"")
        );
    }
}
