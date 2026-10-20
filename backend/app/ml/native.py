"""Lazy native model adapters: no pickle/joblib or training during API requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def fit(
    algorithm: str,
    x: list[list[float]],
    y: np.ndarray,
    names: list[str],
    *,
    validation: tuple[list[list[float]], np.ndarray] | None = None,
    iterations: int = 100,
    seed: int = 20261020,
) -> Any:
    if algorithm == "catboost":
        from catboost import CatBoostRegressor, Pool

        model = CatBoostRegressor(
            iterations=iterations,
            depth=4,
            learning_rate=0.05,
            loss_function="MAE",
            random_seed=seed,
            thread_count=2,
            allow_writing_files=False,
            verbose=False,
        )
        kwargs = (
            {
                "eval_set": Pool(validation[0], validation[1], feature_names=names),
                "early_stopping_rounds": 15,
            }
            if validation
            else {}
        )
        model.fit(Pool(x, y, feature_names=names), **kwargs)
        return model
    if algorithm == "lightgbm":
        import lightgbm as lgb

        dataset = lgb.Dataset(np.array(x), label=y, feature_name=names)
        parameters = dict(
            objective="regression_l1",
            metric="l1",
            verbosity=-1,
            num_threads=2,
            num_leaves=15,
            min_data_in_leaf=5,
            learning_rate=0.05,
            seed=seed,
            deterministic=True,
            force_col_wise=True,
        )
        kwargs: dict[str, Any] = {}
        if validation:
            kwargs.update(
                valid_sets=[
                    lgb.Dataset(np.array(validation[0]), label=validation[1], reference=dataset)
                ],
                callbacks=[lgb.early_stopping(15, verbose=False)],
            )
        return lgb.train(parameters, dataset, num_boost_round=iterations, **kwargs)
    raise ValueError("不支持的学习算法")


def predict(model: Any, values: list[list[float]]) -> np.ndarray:
    result = np.asarray(model.predict(np.asarray(values)), dtype=float).reshape(-1)
    if len(result) != len(values) or not np.isfinite(result).all():
        raise ValueError("模型产生无效预测")
    return np.clip(result, 0, 30)


def save(model: Any, path: Path) -> None:
    model.save_model(str(path))


def load(algorithm: str, path: Path) -> Any:
    if algorithm == "catboost":
        from catboost import CatBoostRegressor

        model = CatBoostRegressor()
        model.load_model(str(path))
        return model
    if algorithm == "lightgbm":
        import lightgbm as lgb

        return lgb.Booster(model_file=str(path))
    raise ValueError("不支持的模型格式")


def contributions(model: Any, algorithm: str, values: list[float]) -> list[float]:
    if algorithm == "catboost":
        from catboost import Pool

        result = model.get_feature_importance(Pool([values]), type="ShapValues")[0][:-1]
    else:
        result = model.predict(np.array([values]), pred_contrib=True)[0][:-1]
    return [float(item) for item in result]
