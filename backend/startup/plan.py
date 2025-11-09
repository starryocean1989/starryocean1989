# -*- coding: utf-8 -*-
"""
启动计划（StartupPlan）

通过 manifest 描述启动节点及其依赖关系，支持阶段级与子阶段级的
DAG 解析，并对外提供拓扑排序、依赖查询等接口。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger("backend.startup.plan")


@dataclass
class StartupNode:
    """启动节点"""

    node_id: str
    label: str
    category: str = "stage"
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StartupPlan:
    """启动计划 DAG"""

    def __init__(self, nodes: Iterable[StartupNode], version: str = "1.0") -> None:
        self.version = version
        self._nodes: Dict[str, StartupNode] = {node.node_id: node for node in nodes}
        self._children: Dict[str, List[str]] = {}
        self._build_relations()

    def _build_relations(self) -> None:
        for node in self._nodes.values():
            for dep in node.depends_on:
                self._children.setdefault(dep, []).append(node.node_id)
            self._children.setdefault(node.node_id, [])

    @classmethod
    def load_default(cls) -> "StartupPlan":
        manifest_path = Path(__file__).with_name("startup_plan.json")
        if not manifest_path.exists():
            raise FileNotFoundError(f"未找到启动计划文件: {manifest_path}")
        return cls.load_from_file(manifest_path)

    @classmethod
    def load_from_file(cls, manifest_path: Path) -> "StartupPlan":
        data = cls._load_manifest(manifest_path)
        version = data.get("version", "1.0")
        nodes = [
            StartupNode(
                node_id=node["id"],
                label=node.get("label", node["id"]),
                category=node.get("category", "stage"),
                depends_on=node.get("depends_on", []),
                metadata=node.get("metadata", {}),
            )
            for node in data.get("nodes", [])
        ]
        plan = cls(nodes, version=version)
        logger.debug("加载启动计划: %s, 节点数=%d", manifest_path, len(nodes))
        cls._validate(plan)
        return plan

    @staticmethod
    def _load_manifest(manifest_path: Path) -> Dict[str, Any]:
        if manifest_path.suffix.lower() in {".json", ".js"}:
            text = manifest_path.read_text(encoding="utf-8")
            return json.loads(text)

        if manifest_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "需要 PyYAML 才能加载 YAML 格式的启动计划，请安装后重试"
                ) from exc
            with manifest_path.open("r", encoding="utf-8") as fp:
                return yaml.safe_load(fp)  # type: ignore[no-any-return]

        raise ValueError(f"不支持的启动计划文件格式: {manifest_path.suffix}")

    @staticmethod
    def _validate(plan: "StartupPlan") -> None:
        for node in plan._nodes.values():
            for dep in node.depends_on:
                if dep not in plan._nodes:
                    raise ValueError(f"节点 {node.node_id} 依赖不存在的节点 {dep}")
        if plan.detect_cycle():
            raise ValueError("启动计划存在循环依赖，请检查 manifest")

    def detect_cycle(self) -> bool:
        visited: Set[str] = set()
        stack: Set[str] = set()

        def _visit(node_id: str) -> bool:
            if node_id in stack:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            stack.add(node_id)
            for child in self._children.get(node_id, []):
                if _visit(child):
                    return True
            stack.remove(node_id)
            return False

        return any(_visit(node_id) for node_id in self._nodes)

    def get_node(self, node_id: str) -> Optional[StartupNode]:
        return self._nodes.get(node_id)

    def get_stage_nodes(self) -> List[StartupNode]:
        return [node for node in self._nodes.values() if node.category == "stage"]

    def get_branch_nodes(self, parent_id: str) -> List[StartupNode]:
        return [
            self._nodes[node_id]
            for node_id in self._children.get(parent_id, [])
            if self._nodes[node_id].category != "stage"
        ]

    def topological_sort(self, *, category: Optional[str] = None) -> List[StartupNode]:
        indegree: Dict[str, int] = {node_id: 0 for node_id in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                indegree[node.node_id] += 1

        queue: List[str] = [
            node_id
            for node_id, node in self._nodes.items()
            if indegree[node_id] == 0
            and (category is None or node.category == category)
        ]

        result: List[StartupNode] = []
        visited: Set[str] = set()

        while queue:
            node_id = queue.pop(0)
            node = self._nodes[node_id]
            if category is None or node.category == category:
                result.append(node)
            visited.add(node_id)
            for child_id in self._children.get(node_id, []):
                indegree[child_id] -= 1
                if indegree[child_id] == 0 and child_id not in visited:
                    queue.append(child_id)

        if len(visited) != len(self._nodes):
            missing = set(self._nodes) - visited
            logger.warning("拓扑排序未覆盖所有节点，剩余: %s", missing)
        return result

    def requires(self, node_id: str) -> List[str]:
        node = self._nodes.get(node_id)
        if not node:
            return []
        return list(node.depends_on)

    def children_of(self, node_id: str) -> List[str]:
        return list(self._children.get(node_id, []))


