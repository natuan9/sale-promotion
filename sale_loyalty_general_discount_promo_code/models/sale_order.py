from odoo import _, models
from odoo.tools import format_amount


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def get_total_saving_specific(self, reward):
        self.ensure_one()
        assert reward.discount_applicability == "specific"
        total_saving = 0
        lines_to_discount = self.env["sale.order.line"]
        order_lines = self.order_line - self._get_no_effect_on_threshold_lines()
        for line in order_lines:
            if not line.product_uom_qty or not line.price_total:
                continue
            domain = reward._get_discount_product_domain()
            if not line.reward_id and line.product_id.filtered_domain(domain):
                lines_to_discount |= line

        for line in lines_to_discount:
            line.discount = reward.discount
            if line.reward_id:
                continue
            total_saving += (
                line.price_unit * line.product_uom_qty * (reward.discount / 100)
            )
        return total_saving

    def get_total_saving_cheapest(self, reward):
        self.ensure_one()
        assert reward.discount_applicability == "cheapest"

        cheapest_line = self._cheapest_line()
        if not cheapest_line:
            return 0
        return (
            cheapest_line.price_unit
            * cheapest_line.product_uom_qty
            * (reward.discount / 100)
        )

    def get_total_saving_order(self, reward):
        self.ensure_one()
        assert reward.discount_applicability == "order"
        total_saving = 0
        for line in self.order_line:
            if line.reward_id:
                continue
            total_saving += (
                line.price_unit * line.product_uom_qty * (reward.discount / 100)
            )
        return total_saving

    def get_total_saving(self, reward):
        total_saving = 0
        reward_applies_on = reward.discount_applicability
        if reward_applies_on == "order":
            total_saving = self.get_total_saving_order(reward)
        elif reward_applies_on == "specific":
            total_saving = self.get_total_saving_specific(reward)
        elif reward_applies_on == "cheapest":
            total_saving = self.get_total_saving_cheapest(reward)
        return total_saving

    def _get_reward_values_discount(self, reward, coupon, **kwargs):
        rewards = super()._get_reward_values_discount(reward, coupon, **kwargs)
        currency = self.pricelist_id.currency_id

        for reward_line in rewards:
            if (
                reward.reward_type == "discount"
                and reward.discount_mode == "percent"
                and (
                    reward.program_id.program_type == "coupons"
                    or reward.program_id.program_type == "promo_code"
                )
            ):
                # Get the saved amount
                # Cannot use the reward_line.price_unit for the saved amount
                # because _get_reward_line_values is called twice.
                # Once in _apply_program_reward and once in _update_programs_and_rewards
                saved_amount = self.get_total_saving(reward)
                formatted_amount = format_amount(self.env, saved_amount, currency)
                reward_line.update(
                    {
                        "name": _(
                            f"You saved {formatted_amount} with promo {coupon.code}"
                        ),
                        "price_unit": 0,
                        "product_uom_qty": 1,
                    }
                )

        return rewards

    def update_discount_percentage(self):
        self.ensure_one()
        reward_lines = self.order_line.filtered(lambda line: line.reward_id)
        order_lines = self.order_line - reward_lines

        for line in order_lines:
            line.discount = 0
            for reward_line in reward_lines:
                reward_applies_on = reward_line.reward_id.discount_applicability
                # If the reward applies on the cheapest line,
                # only want to apply it on the cheapest line
                if reward_applies_on == "cheapest":
                    cheapest_line = self._cheapest_line()
                    if line != cheapest_line:
                        continue

                # only want to apply it on the specific products
                if reward_applies_on == "specific":
                    domain = reward_line.reward_id._get_discount_product_domain()
                    if not line.product_id.filtered_domain(domain):
                        continue

                if (
                    reward_line.reward_id.reward_type
                    and reward_line.reward_id.discount_mode == "percent"
                ):
                    reward_discount = reward_line.reward_id.discount
                    line.discount = 100 - (100 - line.discount) * (
                        1 - reward_discount / 100
                    )

    def _write_vals_from_reward_vals(self, reward_vals, old_lines, delete=True):
        result = super()._write_vals_from_reward_vals(
            reward_vals, old_lines, delete=delete
        )
        self.update_discount_percentage()
        return result
