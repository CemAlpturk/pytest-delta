"""
Dependency graph visualizer for pytest-delta plugin.

Creates visual representations of project dependency graphs to help with
debugging and understanding the plugin's behavior.
"""

from pathlib import Path
from typing import Dict, List, Set, Optional


class DependencyVisualizer:
    """Visualizes dependency graphs in various formats."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def generate_dot_format(self, dependency_graph: Dict[Path, Set[Path]]) -> str:
        """
        Generate DOT format representation of the dependency graph.

        This can be rendered using Graphviz tools if available.

        Args:
            dependency_graph: Dict mapping files to their dependencies

        Returns:
            DOT format string representation of the graph
        """
        lines = ["digraph dependencies {"]
        lines.append("    rankdir=TB;")
        lines.append("    node [shape=box, style=filled, fillcolor=lightblue];")
        lines.append("")

        # Create nodes with relative paths as labels
        node_mapping: Dict[Path, str] = {}
        for file_path in dependency_graph.keys():
            try:
                relative_path = file_path.relative_to(self.root_dir)
                node_id = f"node_{len(node_mapping)}"
                node_mapping[file_path] = node_id

                # Clean path for DOT format
                label = str(relative_path).replace("\\", "/")
                lines.append(f'    {node_id} [label="{label}"];')
            except ValueError:
                # Handle files outside root directory
                node_id = f"node_{len(node_mapping)}"
                node_mapping[file_path] = node_id
                lines.append(f'    {node_id} [label="{file_path.name}"];')

        lines.append("")

        # Add edges for dependencies
        for file_path, dependencies in dependency_graph.items():
            if file_path not in node_mapping:
                continue

            source_node = node_mapping[file_path]
            for dep_path in dependencies:
                if dep_path in node_mapping:
                    target_node = node_mapping[dep_path]
                    lines.append(f"    {source_node} -> {target_node};")

        lines.append("}")
        return "\n".join(lines)

    def generate_text_summary(self, dependency_graph: Dict[Path, Set[Path]]) -> str:
        """
        Generate a human-readable text summary of dependencies.

        Args:
            dependency_graph: Dict mapping files to their dependencies

        Returns:
            Text summary of the dependency graph
        """
        lines = ["Dependency Graph Summary"]
        lines.append("=" * 50)
        lines.append("")

        # Count statistics
        total_files = len(dependency_graph)
        total_dependencies = sum(len(deps) for deps in dependency_graph.values())
        lines.append(f"Total files: {total_files}")
        lines.append(f"Total dependencies: {total_dependencies}")
        lines.append("")

        # Group files by number of dependencies
        by_dep_count: Dict[int, List[Path]] = {}
        for file_path, dependencies in dependency_graph.items():
            count = len(dependencies)
            if count not in by_dep_count:
                by_dep_count[count] = []
            by_dep_count[count].append(file_path)

        lines.append("Files by dependency count:")
        for count in sorted(by_dep_count.keys(), reverse=True):
            files = by_dep_count[count]
            lines.append(f"  {count} dependencies: {len(files)} files")

            # Show files with most dependencies
            if count > 0:
                for file_path in sorted(files)[:5]:  # Show up to 5 files
                    try:
                        rel_path = file_path.relative_to(self.root_dir)
                        lines.append(f"    - {rel_path}")
                    except ValueError:
                        lines.append(f"    - {file_path.name}")

                if len(files) > 5:
                    lines.append(f"    ... and {len(files) - 5} more")

        lines.append("")
        lines.append("Detailed Dependencies:")
        lines.append("-" * 30)

        # Show detailed dependencies for each file
        for file_path, dependencies in sorted(dependency_graph.items()):
            try:
                rel_path = file_path.relative_to(self.root_dir)
                file_label = str(rel_path)
            except ValueError:
                file_label = file_path.name

            lines.append(f"\n{file_label}")

            if dependencies:
                for dep_path in sorted(dependencies):
                    try:
                        dep_rel_path = dep_path.relative_to(self.root_dir)
                        lines.append(f"  -> {dep_rel_path}")
                    except ValueError:
                        lines.append(f"  -> {dep_path.name}")
            else:
                lines.append("  (no dependencies)")

        return "\n".join(lines)

    def save_visualization(
        self,
        dependency_graph: Dict[Path, Set[Path]],
        output_path: Optional[Path] = None,
        format: str = "dot",
    ) -> Path:
        """
        Save dependency graph visualization to file.

        Args:
            dependency_graph: Dict mapping files to their dependencies
            output_path: Optional path for output file. If None, uses default.
            format: Output format ("dot", "txt")

        Returns:
            Path to the generated file
        """
        if output_path is None:
            if format == "dot":
                output_path = self.root_dir / "dependency_graph.dot"
            elif format == "txt":
                output_path = self.root_dir / "dependency_summary.txt"
            else:
                raise ValueError(f"Unsupported format: {format}")

        if format == "dot":
            content = self.generate_dot_format(dependency_graph)
        elif format == "txt":
            content = self.generate_text_summary(dependency_graph)
        else:
            raise ValueError(f"Unsupported format: {format}")

        output_path.write_text(content, encoding="utf-8")
        return output_path

    def generate_console_output(self, dependency_graph: Dict[Path, Set[Path]]) -> str:
        """
        Generate a condensed visualization suitable for console output.

        Args:
            dependency_graph: Dict mapping files to their dependencies

        Returns:
            Condensed text representation
        """
        lines = []
        lines.append("📊 Dependency Graph Visualization")
        lines.append("=" * 50)

        # Statistics
        total_files = len(dependency_graph)
        total_deps = sum(len(deps) for deps in dependency_graph.values())
        max_deps = max(len(deps) for deps in dependency_graph.values()) if dependency_graph else 0

        lines.append(
            f"Files: {total_files} | Dependencies: {total_deps} | Max per file: {max_deps}"
        )
        lines.append("")

        # Show files with most dependencies (top 10)
        files_with_deps = [
            (file_path, len(dependencies)) for file_path, dependencies in dependency_graph.items()
        ]
        files_with_deps.sort(key=lambda x: x[1], reverse=True)

        lines.append("🔗 Files with most dependencies:")
        for file_path, dep_count in files_with_deps[:10]:
            try:
                rel_path = file_path.relative_to(self.root_dir)
                path_str = str(rel_path)
                # Truncate long paths
                if len(path_str) > 40:
                    path_str = "..." + path_str[-37:]
                lines.append(f"  {dep_count:2d} deps: {path_str}")
            except ValueError:
                lines.append(f"  {dep_count:2d} deps: {file_path.name}")

        return "\n".join(lines)
