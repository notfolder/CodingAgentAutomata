"""
eBPF 利用可否を判定するモジュール。

BTF ファイルの存在と Linux ケーパビリティ（CAP_BPF / CAP_PERFMON）を確認し、
Tracee による TTY 待機検知が実行可能かどうかを判定する。
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

# ロガーを設定
logger = logging.getLogger(__name__)

# BTF（BPF Type Format）カーネル情報ファイルのパス
_BTF_PATH = "/sys/kernel/btf/vmlinux"

# CAP_BPF のビット番号（Linux 5.8 以降）
_CAP_BPF_BIT = 39
# CAP_PERFMON のビット番号（Linux 5.8 以降）
_CAP_PERFMON_BIT = 38


class EBPFEnvironmentChecker:
    """
    eBPF を使用するための環境要件を確認するクラス。

    BTF ファイルの存在確認と Linux ケーパビリティの確認を行い、
    Tracee による TTY 待機検知が利用可能かどうかを判定する。
    """

    def check_btf(self) -> bool:
        """
        BTF（BPF Type Format）カーネル情報ファイルの存在を確認する。

        /sys/kernel/btf/vmlinux が存在する場合、eBPF プログラムの
        ポータビリティ（CO-RE）に必要な情報が利用可能であることを示す。

        Returns:
            bool: BTF ファイルが存在する場合は True、存在しない場合は False
        """
        exists = os.path.exists(_BTF_PATH)
        if exists:
            logger.debug("EBPFEnvironmentChecker.check_btf: BTF ファイルが存在します path=%s", _BTF_PATH)
        else:
            logger.warning(
                "EBPFEnvironmentChecker.check_btf: BTF ファイルが見つかりません path=%s",
                _BTF_PATH,
            )
        return exists

    def check_caps(self) -> bool:
        """
        /proc/self/status の CapEff ビットを確認し、
        CAP_BPF（ビット39）または CAP_PERFMON（ビット38）のどちらかを
        保持しているかチェックする。

        どちらかのケーパビリティがあれば eBPF を使用できる可能性がある。

        Returns:
            bool: CAP_BPF または CAP_PERFMON を保持している場合は True
        """
        try:
            # /proc/self/status から CapEff 行を読み取る
            cap_eff_hex: Optional[str] = None
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("CapEff:"):
                        # "CapEff:\t0000000000000000" 形式をパース
                        cap_eff_hex = line.split(":")[1].strip()
                        break

            if cap_eff_hex is None:
                logger.warning(
                    "EBPFEnvironmentChecker.check_caps: CapEff 行が見つかりません"
                )
                return False

            # 16進数を整数に変換してビットチェック（不正な形式の場合は安全に処理）
            try:
                cap_eff: int = int(cap_eff_hex, 16)
            except ValueError:
                logger.warning(
                    "EBPFEnvironmentChecker.check_caps: CapEff 値の解析に失敗しました value='%s'",
                    cap_eff_hex,
                )
                return False
            has_cap_bpf: bool = bool(cap_eff & (1 << _CAP_BPF_BIT))
            has_cap_perfmon: bool = bool(cap_eff & (1 << _CAP_PERFMON_BIT))

            result = has_cap_bpf or has_cap_perfmon
            logger.debug(
                "EBPFEnvironmentChecker.check_caps: CapEff=0x%s, "
                "CAP_BPF=%s, CAP_PERFMON=%s",
                cap_eff_hex,
                has_cap_bpf,
                has_cap_perfmon,
            )
            if not result:
                logger.warning(
                    "EBPFEnvironmentChecker.check_caps: "
                    "CAP_BPF および CAP_PERFMON のどちらも保持していません"
                )
            return result

        except Exception as exc:
            logger.warning(
                "EBPFEnvironmentChecker.check_caps: ケーパビリティ確認中にエラーが発生しました: %s",
                exc,
            )
            return False

    def evaluate(self, timeout_sec: float = 5.0) -> bool:
        """
        eBPF 環境が利用可能かどうかを総合的に判定する。

        check_btf() と check_caps() を実行し、両方が True の場合のみ
        eBPF が利用可能と判断する。timeout_sec 秒以内に完了しない場合は
        タイムアウトとして False を返す。

        Args:
            timeout_sec: 判定処理のタイムアウト秒数（デフォルト: 5.0秒）

        Returns:
            bool: eBPF が利用可能な場合は True、そうでない場合は False
        """
        def _run_checks() -> bool:
            """BTF 確認とケーパビリティ確認を順に実行する。"""
            btf_ok = self.check_btf()
            if not btf_ok:
                return False
            caps_ok = self.check_caps()
            return caps_ok

        # タイムアウト付きでチェックを実行する
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_checks)
            try:
                result = future.result(timeout=timeout_sec)
                if not result:
                    logger.warning(
                        "EBPFEnvironmentChecker.evaluate: eBPF 環境要件を満たしていないため"
                        "TTY 検知を無効化します"
                    )
                return result
            except FuturesTimeoutError:
                logger.warning(
                    "EBPFEnvironmentChecker.evaluate: eBPF 環境確認が %.1f 秒でタイムアウトしました。"
                    "TTY 検知を無効化します",
                    timeout_sec,
                )
                return False
            except Exception as exc:
                logger.warning(
                    "EBPFEnvironmentChecker.evaluate: eBPF 環境確認中にエラーが発生しました。"
                    "TTY 検知を無効化します: %s",
                    exc,
                )
                return False
