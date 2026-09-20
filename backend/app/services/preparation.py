from __future__ import annotations

from typing import Any
import ast

import numpy as np
import pandas as pd


COMPARATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "is_null", "not_null"}


def _require_column(df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise ValueError(f"Colonne introuvable: {column}")


def _numeric(series: pd.Series, column: str) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    if out.notna().sum() == 0:
        raise ValueError(f"La colonne '{column}' ne contient aucune valeur numérique exploitable.")
    return out



def _evaluate_expression(df: pd.DataFrame, expression: str) -> pd.Series:
    """Safely evaluate a small arithmetic DSL; no Python eval and no attribute access."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Expression invalide: {exc.msg}") from exc

    def walk(node: ast.AST):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Seules les constantes numériques sont autorisées hors col().")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.Pow): return left ** right
            return left % right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name == "col":
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError('Utilisez col("NomColonne").')
                column = node.args[0].value
                _require_column(df, column)
                return _numeric(df[column], column)
            if name in {"abs", "sqrt", "log", "log1p", "round"}:
                if len(node.args) != 1:
                    raise ValueError(f"{name}() attend un seul argument.")
                value = walk(node.args[0])
                if name == "abs": return np.abs(value)
                if name == "sqrt": return np.sqrt(value)
                if name == "log": return np.log(value)
                if name == "log1p": return np.log1p(value)
                return np.round(value)
            raise ValueError(f"Fonction non autorisée: {name}")
        raise ValueError("Expression non autorisée. Utilisez col(\"Nom\"), nombres, + - * / ** %, abs, sqrt, log, log1p ou round.")

    result = walk(tree)
    if isinstance(result, pd.Series):
        return result.replace([np.inf, -np.inf], np.nan)
    return pd.Series(result, index=df.index, dtype=float)


def combine_dataframes(left: pd.DataFrame, right: pd.DataFrame, op: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Combine two datasets deterministically for join/concat workflows."""
    kind = str(op.get("type", "")).strip()
    if kind == "merge":
        left_on = [str(x) for x in op.get("left_on", [])]
        right_on = [str(x) for x in op.get("right_on", [])]
        how = str(op.get("how", "inner"))
        if how not in {"inner", "left", "right", "outer"}:
            raise ValueError("Type de jointure non supporté.")
        if not left_on or not right_on or len(left_on) != len(right_on):
            raise ValueError("Les clés gauche/droite doivent être renseignées et avoir la même longueur.")
        for c in left_on: _require_column(left, c)
        for c in right_on: _require_column(right, c)
        out = left.merge(right, how=how, left_on=left_on, right_on=right_on, suffixes=("__left", "__right"), validate=None)
        return out, {"type": "combine_merge", "label": f"Jointure {how} sur {len(left_on)} clé(s)", "params": {"left_on": left_on, "right_on": right_on, "how": how}}
    if kind == "concat_rows":
        join = str(op.get("join", "outer"))
        if join not in {"outer", "inner"}: raise ValueError("Alignement concat invalide.")
        out = pd.concat([left, right], axis=0, ignore_index=True, join=join, sort=False)
        return out, {"type": "combine_concat_rows", "label": "Concaténer les lignes", "params": {"join": join}}
    if kind == "concat_columns":
        if len(left) != len(right):
            raise ValueError("La concaténation de colonnes exige le même nombre de lignes.")
        l, r = left.reset_index(drop=True).copy(), right.reset_index(drop=True).copy()
        overlap = set(l.columns) & set(r.columns)
        if overlap:
            r = r.rename(columns={c: f"{c}__right" for c in overlap})
        out = pd.concat([l, r], axis=1)
        return out, {"type": "combine_concat_columns", "label": "Concaténer les colonnes", "params": {"renamed_overlaps": sorted(overlap)}}
    raise ValueError(f"Combinaison non supportée: {kind}")


def apply_operation(df: pd.DataFrame, op: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply one auditable, deterministic transformation to a dataframe copy."""
    kind = str(op.get("type", "")).strip()
    out = df.copy(deep=True)

    if kind == "rename_column":
        column, new_name = str(op.get("column", "")), str(op.get("new_name", "")).strip()
        _require_column(out, column)
        if not new_name:
            raise ValueError("Le nouveau nom ne peut pas être vide.")
        if new_name != column and new_name in out.columns:
            raise ValueError(f"Une colonne '{new_name}' existe déjà.")
        out = out.rename(columns={column: new_name})
        return out, {"type": kind, "label": f"Renommer {column} → {new_name}", "params": {"column": column, "new_name": new_name}}

    if kind == "drop_columns":
        columns = [str(x) for x in op.get("columns", [])]
        if not columns:
            raise ValueError("Sélectionnez au moins une colonne à supprimer.")
        for column in columns:
            _require_column(out, column)
        if len(columns) >= len(out.columns):
            raise ValueError("Impossible de supprimer toutes les colonnes du dataset.")
        out = out.drop(columns=columns)
        return out, {"type": kind, "label": f"Supprimer {len(columns)} colonne(s)", "params": {"columns": columns}}

    if kind == "remove_duplicates":
        subset = [str(x) for x in (op.get("subset") or [])] or None
        if subset:
            for column in subset:
                _require_column(out, column)
        before = len(out)
        out = out.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
        removed = before - len(out)
        return out, {"type": kind, "label": f"Supprimer les doublons ({removed} supprimé(s))", "params": {"subset": subset, "removed": removed}}

    if kind == "fill_missing":
        column = str(op.get("column", ""))
        strategy = str(op.get("strategy", "median"))
        _require_column(out, column)
        missing_before = int(out[column].isna().sum())
        if strategy in {"mean", "median"}:
            s = _numeric(out[column], column)
            fill = float(s.mean()) if strategy == "mean" else float(s.median())
            out[column] = s.fillna(fill)
        elif strategy == "mode":
            mode = out[column].mode(dropna=True)
            if mode.empty:
                raise ValueError(f"Aucune modalité disponible pour imputer '{column}'.")
            fill = mode.iloc[0]
            out[column] = out[column].fillna(fill)
        elif strategy == "constant":
            fill = op.get("value")
            if fill is None:
                raise ValueError("Une valeur constante est requise.")
            out[column] = out[column].fillna(fill)
        else:
            raise ValueError(f"Stratégie d'imputation non supportée: {strategy}")
        return out, {"type": kind, "label": f"Imputer {column} ({strategy})", "params": {"column": column, "strategy": strategy, "value": fill, "missing_before": missing_before}}

    if kind == "cast_type":
        column, dtype = str(op.get("column", "")), str(op.get("dtype", "string"))
        _require_column(out, column)
        if dtype == "string":
            out[column] = out[column].astype("string")
        elif dtype == "float":
            out[column] = pd.to_numeric(out[column], errors="raise").astype(float)
        elif dtype == "integer":
            numeric = pd.to_numeric(out[column], errors="raise")
            if numeric.dropna().mod(1).ne(0).any():
                raise ValueError(f"'{column}' contient des valeurs décimales incompatibles avec integer.")
            out[column] = numeric.astype("Int64")
        elif dtype == "boolean":
            values = out[column]
            if pd.api.types.is_bool_dtype(values):
                out[column] = values.astype("boolean")
            else:
                mapping = {"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False, "oui": True, "non": False}
                converted = values.map(lambda x: mapping.get(str(x).strip().lower()) if pd.notna(x) else pd.NA)
                if converted.isna().sum() > values.isna().sum():
                    raise ValueError(f"Certaines valeurs de '{column}' ne peuvent pas être converties en booléen.")
                out[column] = converted.astype("boolean")
        elif dtype == "datetime":
            out[column] = pd.to_datetime(out[column], errors="raise")
        elif dtype == "category":
            out[column] = out[column].astype("category")
        else:
            raise ValueError(f"Type cible non supporté: {dtype}")
        return out, {"type": kind, "label": f"Convertir {column} en {dtype}", "params": {"column": column, "dtype": dtype}}

    if kind == "filter_rows":
        column, operator = str(op.get("column", "")), str(op.get("operator", "eq"))
        _require_column(out, column)
        if operator not in COMPARATORS:
            raise ValueError(f"Opérateur non supporté: {operator}")
        s = out[column]
        value = op.get("value")
        if operator in {"is_null", "not_null"}:
            mask = s.isna() if operator == "is_null" else s.notna()
        elif operator in {"contains", "not_contains"}:
            mask = s.astype("string").str.contains(str(value), case=False, na=False, regex=False)
            if operator == "not_contains":
                mask = ~mask
        elif operator in {"gt", "gte", "lt", "lte"}:
            numeric = _numeric(s, column)
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("La valeur du filtre doit être numérique.") from exc
            mask = {"gt": numeric > numeric_value, "gte": numeric >= numeric_value, "lt": numeric < numeric_value, "lte": numeric <= numeric_value}[operator]
        else:
            if pd.api.types.is_numeric_dtype(s):
                try:
                    compare_value = float(value)
                    mask = pd.to_numeric(s, errors="coerce") == compare_value
                except (TypeError, ValueError):
                    mask = s.astype("string") == str(value)
            else:
                mask = s.astype("string") == str(value)
            if operator == "ne":
                mask = ~mask
        before = len(out)
        out = out.loc[mask.fillna(False)].reset_index(drop=True)
        return out, {"type": kind, "label": f"Filtrer {column} ({operator})", "params": {"column": column, "operator": operator, "value": value, "rows_before": before, "rows_after": len(out)}}

    if kind == "sort_rows":
        column = str(op.get("column", ""))
        ascending = bool(op.get("ascending", True))
        _require_column(out, column)
        out = out.sort_values(column, ascending=ascending, kind="mergesort", na_position="last").reset_index(drop=True)
        return out, {"type": kind, "label": f"Trier {column} ({'croissant' if ascending else 'décroissant'})", "params": {"column": column, "ascending": ascending}}

    if kind == "clip_outliers_iqr":
        column = str(op.get("column", ""))
        factor = float(op.get("factor", 1.5))
        mode = str(op.get("mode", "clip"))
        _require_column(out, column)
        if factor <= 0:
            raise ValueError("Le facteur IQR doit être positif.")
        s = _numeric(out[column], column)
        q1, q3 = float(s.quantile(.25)), float(s.quantile(.75))
        iqr = q3 - q1
        low, high = q1 - factor * iqr, q3 + factor * iqr
        mask = s.notna() & ((s < low) | (s > high))
        affected = int(mask.sum())
        if mode == "clip":
            out[column] = s.clip(lower=low, upper=high)
        elif mode == "remove":
            out = out.loc[~mask].reset_index(drop=True)
        else:
            raise ValueError("Mode outlier non supporté: utilisez 'clip' ou 'remove'.")
        return out, {"type": kind, "label": f"Outliers IQR sur {column} ({mode}, {affected})", "params": {"column": column, "factor": factor, "mode": mode, "lower": low, "upper": high, "affected": affected}}

    if kind == "standardize":
        columns = [str(x) for x in op.get("columns", [])]
        if not columns:
            raise ValueError("Sélectionnez au moins une colonne numérique.")
        for column in columns:
            _require_column(out, column)
            s = _numeric(out[column], column)
            std = float(s.std(ddof=0))
            if std == 0 or not np.isfinite(std):
                raise ValueError(f"Impossible de standardiser la colonne constante '{column}'.")
            out[column] = (s - float(s.mean())) / std
        return out, {"type": kind, "label": f"Standardiser {len(columns)} colonne(s)", "params": {"columns": columns}}

    if kind == "normalize_minmax":
        columns = [str(x) for x in op.get("columns", [])]
        if not columns:
            raise ValueError("Sélectionnez au moins une colonne numérique.")
        for column in columns:
            _require_column(out, column)
            s = _numeric(out[column], column)
            minimum, maximum = float(s.min()), float(s.max())
            if maximum == minimum:
                raise ValueError(f"Impossible de normaliser la colonne constante '{column}'.")
            out[column] = (s - minimum) / (maximum - minimum)
        return out, {"type": kind, "label": f"Normaliser Min-Max {len(columns)} colonne(s)", "params": {"columns": columns}}


    if kind == "one_hot_encode":
        columns = [str(x) for x in op.get("columns", [])]
        if not columns:
            raise ValueError("Sélectionnez au moins une colonne catégorielle.")
        for column in columns:
            _require_column(out, column)
        prefix_sep = str(op.get("prefix_sep", "__"))
        before_cols = list(out.columns)
        out = pd.get_dummies(out, columns=columns, prefix=columns, prefix_sep=prefix_sep, dtype=int)
        created = [c for c in out.columns if c not in before_cols]
        return out, {"type": kind, "label": f"Encoder one-hot {len(columns)} colonne(s)", "params": {"columns": columns, "created_columns": created}}

    if kind == "add_calculated_column":
        new_name = str(op.get("new_name", "")).strip()
        expression = str(op.get("expression", "")).strip()
        if not new_name:
            raise ValueError("Le nom de la nouvelle colonne est requis.")
        if new_name in out.columns:
            raise ValueError(f"La colonne '{new_name}' existe déjà.")
        if not expression:
            raise ValueError("Une expression est requise.")
        out[new_name] = _evaluate_expression(out, expression)
        return out, {"type": kind, "label": f"Créer la variable {new_name}", "params": {"new_name": new_name, "expression": expression}}

    if kind == "groupby_aggregate":
        group_by = [str(x) for x in op.get("group_by", [])]
        aggregations = op.get("aggregations", [])
        if not group_by:
            raise ValueError("Sélectionnez au moins une variable de regroupement.")
        if not aggregations:
            raise ValueError("Ajoutez au moins une agrégation.")
        for column in group_by:
            _require_column(out, column)
        allowed = {"mean", "sum", "min", "max", "median", "count", "nunique", "std", "var", "first", "last"}
        named: dict[str, pd.NamedAgg] = {}
        normalized = []
        for idx, item in enumerate(aggregations):
            column = str(item.get("column", ""))
            function = str(item.get("function", "mean"))
            _require_column(out, column)
            if function not in allowed:
                raise ValueError(f"Agrégation non supportée: {function}")
            alias = str(item.get("alias") or f"{column}_{function}").strip()
            if not alias or alias in group_by or alias in named:
                alias = f"{column}_{function}_{idx+1}"
            named[alias] = pd.NamedAgg(column=column, aggfunc=function)
            normalized.append({"column": column, "function": function, "alias": alias})
        out = out.groupby(group_by, dropna=False, observed=True).agg(**named).reset_index()
        return out, {"type": kind, "label": f"Agréger par {', '.join(group_by)}", "params": {"group_by": group_by, "aggregations": normalized}}

    if kind == "pivot_table":
        index = [str(x) for x in op.get("index", [])]
        columns = str(op.get("columns", ""))
        values = str(op.get("values", ""))
        aggfunc = str(op.get("aggfunc", "mean"))
        allowed = {"mean", "sum", "min", "max", "median", "count"}
        if not index or not columns or not values:
            raise ValueError("Index, colonne de pivot et valeur sont requis.")
        if aggfunc not in allowed:
            raise ValueError(f"Agrégation de pivot non supportée: {aggfunc}")
        for column in [*index, columns, values]:
            _require_column(out, column)
        if columns in index or values in index or columns == values:
            raise ValueError("Index, colonne de pivot et valeur doivent être distincts.")
        pivot = pd.pivot_table(out, index=index, columns=columns, values=values, aggfunc=aggfunc, dropna=False)
        if isinstance(pivot.columns, pd.MultiIndex):
            pivot.columns = ["__".join(str(x) for x in col if str(x) != "") for col in pivot.columns]
        else:
            pivot.columns = [f"{values}__{c}" for c in pivot.columns]
        out = pivot.reset_index()
        return out, {"type": kind, "label": f"Pivot {values} par {columns}", "params": {"index": index, "columns": columns, "values": values, "aggfunc": aggfunc}}

    if kind == "melt_unpivot":
        id_vars = [str(x) for x in op.get("id_vars", [])]
        value_vars = [str(x) for x in op.get("value_vars", [])]
        var_name = str(op.get("var_name", "variable")).strip() or "variable"
        value_name = str(op.get("value_name", "value")).strip() or "value"
        if not value_vars:
            raise ValueError("Sélectionnez au moins une colonne à dé-pivoter.")
        for column in [*id_vars, *value_vars]:
            _require_column(out, column)
        if set(id_vars) & set(value_vars):
            raise ValueError("Une colonne ne peut pas être à la fois identifiante et dé-pivotée.")
        if var_name == value_name:
            raise ValueError("Les noms des colonnes variable et valeur doivent être différents.")
        out = out.melt(id_vars=id_vars, value_vars=value_vars, var_name=var_name, value_name=value_name)
        return out, {"type": kind, "label": f"Unpivot {len(value_vars)} colonne(s)", "params": {"id_vars": id_vars, "value_vars": value_vars, "var_name": var_name, "value_name": value_name}}

    if kind == "extract_date_parts":
        column = str(op.get("column", ""))
        parts = [str(x) for x in op.get("parts", [])]
        _require_column(out, column)
        allowed = {"year", "quarter", "month", "day", "weekday", "hour"}
        parts = [p for p in parts if p in allowed]
        if not parts:
            raise ValueError("Sélectionnez au moins une composante de date.")
        dates = pd.to_datetime(out[column], errors="coerce")
        if dates.notna().sum() == 0:
            raise ValueError(f"La colonne '{column}' ne contient aucune date exploitable.")
        for part in parts:
            name = f"{column}__{part}"
            if part == "year": out[name] = dates.dt.year.astype("Int64")
            elif part == "quarter": out[name] = dates.dt.quarter.astype("Int64")
            elif part == "month": out[name] = dates.dt.month.astype("Int64")
            elif part == "day": out[name] = dates.dt.day.astype("Int64")
            elif part == "weekday": out[name] = dates.dt.weekday.astype("Int64")
            elif part == "hour": out[name] = dates.dt.hour.astype("Int64")
        return out, {"type": kind, "label": f"Extraire {len(parts)} composante(s) de {column}", "params": {"column": column, "parts": parts}}

    if kind == "bin_numeric":
        column = str(op.get("column", ""))
        new_name = str(op.get("new_name") or f"{column}__bin").strip()
        method = str(op.get("method", "quantile")).strip()
        bins = int(op.get("bins", 4))
        _require_column(out, column)
        if not new_name:
            raise ValueError("Le nom de la variable discrétisée est requis.")
        if new_name != column and new_name in out.columns:
            raise ValueError(f"La colonne '{new_name}' existe déjà.")
        if method not in {"quantile", "width"}:
            raise ValueError("Méthode de discrétisation non supportée: utilisez 'quantile' ou 'width'.")
        if bins < 2 or bins > 100:
            raise ValueError("Le nombre de classes doit être compris entre 2 et 100.")
        values = _numeric(out[column], column)
        try:
            if method == "quantile":
                bucketed = pd.qcut(values, q=bins, duplicates="drop")
            else:
                bucketed = pd.cut(values, bins=bins, duplicates="drop")
        except ValueError as exc:
            raise ValueError(f"Discrétisation impossible pour '{column}': {exc}") from exc
        categories = [str(x) for x in getattr(bucketed.dtype, "categories", [])]
        if len(categories) < 2:
            raise ValueError(f"La colonne '{column}' ne permet pas de créer au moins deux classes.")
        out[new_name] = bucketed.astype("string")
        return out, {"type": kind, "label": f"Discrétiser {column} ({method}, {len(categories)} classes)", "params": {"column": column, "new_name": new_name, "method": method, "bins": bins, "categories": categories}}

    if kind == "lag_feature":
        column = str(op.get("column", ""))
        periods = int(op.get("periods", 1))
        new_name = str(op.get("new_name") or f"{column}__lag{periods}").strip()
        group_by = [str(x) for x in op.get("group_by", [])]
        order_by = str(op.get("order_by") or "").strip() or None
        _require_column(out, column)
        for name in group_by:
            _require_column(out, name)
        if order_by:
            _require_column(out, order_by)
        if periods < 1 or periods > 10000:
            raise ValueError("Le décalage doit être compris entre 1 et 10000 périodes.")
        if not new_name or (new_name != column and new_name in out.columns):
            raise ValueError(f"Nom de variable de lag invalide ou déjà utilisé: '{new_name}'.")
        work = out.copy()
        marker = "__dv_original_order__"
        while marker in work.columns:
            marker += "_"
        work[marker] = np.arange(len(work))
        sort_cols = [*group_by, *([order_by] if order_by else [])]
        if sort_cols:
            work = work.sort_values(sort_cols, kind="mergesort", na_position="last")
        if group_by:
            work[new_name] = work.groupby(group_by, dropna=False, observed=True)[column].shift(periods)
        else:
            work[new_name] = work[column].shift(periods)
        out = work.sort_values(marker, kind="mergesort").drop(columns=[marker]).reset_index(drop=True)
        return out, {"type": kind, "label": f"Lag {periods} de {column}", "params": {"column": column, "new_name": new_name, "periods": periods, "group_by": group_by, "order_by": order_by}}

    if kind == "rolling_feature":
        column = str(op.get("column", ""))
        window = int(op.get("window", 3))
        function = str(op.get("function", "mean"))
        min_periods = int(op.get("min_periods", 1))
        new_name = str(op.get("new_name") or f"{column}__rolling_{function}_{window}").strip()
        group_by = [str(x) for x in op.get("group_by", [])]
        order_by = str(op.get("order_by") or "").strip() or None
        _require_column(out, column)
        for name in group_by:
            _require_column(out, name)
        if order_by:
            _require_column(out, order_by)
        allowed = {"mean", "sum", "min", "max", "median", "std"}
        if function not in allowed:
            raise ValueError(f"Agrégation rolling non supportée: {function}")
        if window < 2 or window > 10000:
            raise ValueError("La fenêtre rolling doit être comprise entre 2 et 10000 lignes.")
        if min_periods < 1 or min_periods > window:
            raise ValueError("min_periods doit être compris entre 1 et la taille de fenêtre.")
        if not new_name or (new_name != column and new_name in out.columns):
            raise ValueError(f"Nom de variable rolling invalide ou déjà utilisé: '{new_name}'.")
        work = out.copy()
        work[column] = _numeric(work[column], column)
        marker = "__dv_original_order__"
        while marker in work.columns:
            marker += "_"
        work[marker] = np.arange(len(work))
        sort_cols = [*group_by, *([order_by] if order_by else [])]
        if sort_cols:
            work = work.sort_values(sort_cols, kind="mergesort", na_position="last")
        if group_by:
            work[new_name] = work.groupby(group_by, dropna=False, observed=True)[column].transform(
                lambda series: series.rolling(window=window, min_periods=min_periods).agg(function)
            )
        else:
            work[new_name] = work[column].rolling(window=window, min_periods=min_periods).agg(function)
        out = work.sort_values(marker, kind="mergesort").drop(columns=[marker]).reset_index(drop=True)
        return out, {"type": kind, "label": f"Rolling {function}({window}) de {column}", "params": {"column": column, "new_name": new_name, "window": window, "function": function, "min_periods": min_periods, "group_by": group_by, "order_by": order_by}}

    raise ValueError(f"Transformation non supportée: {kind}")
